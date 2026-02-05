from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import asyncio
import json
from app.domains.admin.models import AdminOut
from app.domains.admin.service import AdminService
from app.domains.user.models import User
from app.domains.user.schemas import UserCreate, UserUpdate
from app.domains.user.repository import UserRepository
from app.domains.attendance.repository import AttendanceRepository
from app.domains.system_log.repository import SystemLogRepository
from app.domains.system_log.models import SystemLog
from app.dependencies import (
    get_admin_service, 
    get_current_admin, 
    require_admin_role,
    get_user_repository,
    get_attendance_repository,
    get_system_log_repository,
    get_admin_repository,
    get_notification_service,
    get_message_service,
    security
)
from app.domains.notification.models import (
    NotificationPriority,
    NotificationCategory,
    MessageType,
    MessageTarget
)
from app.domains.notification.service import NotificationService, MessageService

router = APIRouter(prefix="/admin", tags=["Admin"])

# Request/Response Models
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str
    admin: AdminOut
    token_type: str = "bearer"

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    new_password: str = Field(..., min_length=6)


class DashboardActivityItem(BaseModel):
    id: str
    timestamp: str
    type: str
    stage: Optional[str] = None
    status: str
    title: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    device_id: Optional[str] = None
    session_id: Optional[str] = None


class DashboardOverviewResponse(BaseModel):
    total_users: int
    today_attendance_count: int
    currently_checked_in_users: int
    failed_recognition_today: int
    failed_liveness_today: int
    system_status: str  # online | degraded | offline
    recent_activity: List[DashboardActivityItem]

# Authentication Endpoints
@router.post("/auth/login", response_model=LoginResponse)
async def login(
    credentials: LoginRequest,
    admin_service: AdminService = Depends(get_admin_service)
):
    """Admin login"""
    token, admin = await admin_service.authenticate(credentials.email, credentials.password)
    return LoginResponse(access_token=token, admin=admin)

@router.post("/auth/logout")
async def logout(current_admin: AdminOut = Depends(get_current_admin)):
    """Admin logout (client should remove token)"""
    return {"message": "Logged out successfully"}

@router.get("/auth/me", response_model=AdminOut)
async def get_me(current_admin: AdminOut = Depends(get_current_admin)):
    """Get current admin info"""
    return current_admin


@router.get("/dashboard/overview", response_model=DashboardOverviewResponse)
async def dashboard_overview(
    current_admin: AdminOut = Depends(get_current_admin),
    user_repo: UserRepository = Depends(get_user_repository),
    attendance_repo: AttendanceRepository = Depends(get_attendance_repository),
    system_log_repo: SystemLogRepository = Depends(get_system_log_repository),
):
    """
    Level 2 (4) Dashboard overview: real-time operational KPIs + recent activity feed.
    """
    # "Today" is computed in UTC for consistency (frontend displays in local time)
    now_utc = datetime.now(timezone.utc)
    start_of_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    # System status: online if DB is reachable
    system_status = "online"
    try:
        # Motor collections expose database -> client
        await user_repo.collection.database.client.admin.command("ping")
    except Exception:
        system_status = "offline"

    # Total users
    total_users = await user_repo.collection.count_documents({})

    # Today's attendance count (attendance_logs collection - core entity)
    today_attendance_count = await attendance_repo.collection.count_documents(
        {"timestamp": {"$gte": start_of_day, "$lt": end_of_day}}
    )

    # Currently checked-in users = users whose latest event is check_in (across all time)
    # Using aggregation: sort desc, group by user_id, take first event_type, then match check_in.
    pipeline = [
        {"$sort": {"timestamp": -1}},
        {"$group": {"_id": "$user_id", "latest_event_type": {"$first": "$event_type"}}},
        {"$match": {"latest_event_type": "check_in"}},
        {"$count": "count"},
    ]
    agg = await attendance_repo.collection.aggregate(pipeline).to_list(length=1)
    currently_checked_in_users = agg[0]["count"] if agg else 0

    # Failed recognition today (system logs)
    recognition_logs = system_log_repo.collections["recognition_logs"]
    failed_recognition_today = await recognition_logs.count_documents(
        {"type": "attendance_recognition", "stage": "failed", "timestamp": {"$gte": start_of_day, "$lt": end_of_day}}
    )

    # Failed liveness today (system logs)
    liveness_logs = system_log_repo.collections["liveness_logs"]
    failed_liveness_today = await liveness_logs.count_documents(
        {"type": "liveness", "stage": "failed", "timestamp": {"$gte": start_of_day, "$lt": end_of_day}}
    )

    # Recent activity (merge last events from multiple collections)
    # We pull a few from each, then merge by timestamp.
    attendance_cursor = attendance_repo.collection.find(
        {"timestamp": {"$gte": start_of_day, "$lt": end_of_day}}
    ).sort("timestamp", -1).limit(10)
    recognition_cursor = recognition_logs.find(
        {"timestamp": {"$gte": start_of_day, "$lt": end_of_day}}
    ).sort("timestamp", -1).limit(10)
    liveness_cursor = liveness_logs.find(
        {"timestamp": {"$gte": start_of_day, "$lt": end_of_day}}
    ).sort("timestamp", -1).limit(10)

    attendance_docs = await attendance_cursor.to_list(length=10)
    recognition_docs = await recognition_cursor.to_list(length=10)
    liveness_docs = await liveness_cursor.to_list(length=10)

    # Collect user ids to resolve names in one pass
    user_ids = set()
    for d in attendance_docs:
        if d.get("user_id"):
            user_ids.add(d["user_id"])
    for d in recognition_docs:
        if d.get("user_id"):
            user_ids.add(d["user_id"])
    for d in liveness_docs:
        if d.get("user_id"):
            user_ids.add(d["user_id"])

    user_name_by_id = {}
    for uid in user_ids:
        try:
            user = await user_repo.get_user_by_id(str(uid))
            if user:
                user_name_by_id[str(uid)] = user.name
        except Exception:
            continue

    def iso(ts: datetime) -> str:
        # Ensure ISO string; if naive, assume UTC
        if ts is None:
            return ""
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()

    activity: List[DashboardActivityItem] = []

    # Attendance events - ONLY show successful attendance (liveness passed)
    # Failed liveness attempts should NOT create attendance records, but if they exist, mark as failed
    for d in attendance_docs:
        ts = d.get("timestamp")
        uid = str(d.get("user_id")) if d.get("user_id") else None
        event_type = d.get("event_type") or "check_in"
        liveness = d.get("liveness")
        # CRITICAL: Only mark as success if liveness is explicitly "passed"
        # If liveness is None, "failed", or anything else, mark as failed
        # This ensures failed attempts are correctly displayed
        if liveness == "passed":
            status = "success"
        else:
            status = "failed"
            # Log warning if we see a failed attendance record (shouldn't happen)
            print(f"⚠️ WARNING: Found attendance record with liveness={liveness} - this should not exist!")
        activity.append(
            DashboardActivityItem(
                id=str(d.get("_id")),
                timestamp=iso(ts),
                type="attendance",
                stage=event_type,
                status=status,
                title=f"Attendance {event_type.replace('_', ' ')}",
                user_id=uid,
                user_name=user_name_by_id.get(uid) if uid else None,
                device_id=d.get("device_id"),
                session_id=d.get("session_id"),
            )
        )

    # Recognition events
    for d in recognition_docs:
        ts = d.get("timestamp")
        uid = str(d.get("user_id")) if d.get("user_id") else None
        stage = d.get("stage") or "unknown"
        status = "failed" if stage == "failed" else "success" if stage == "success" else "info"
        activity.append(
            DashboardActivityItem(
                id=str(d.get("_id")),
                timestamp=iso(ts),
                type="recognition",
                stage=stage,
                status=status,
                title="Face recognition",
                user_id=uid,
                user_name=user_name_by_id.get(uid) if uid else None,
                device_id=d.get("device_id"),
                session_id=d.get("session_id"),
            )
        )

    # Liveness events - Show ALL liveness attempts (both passed and failed)
    # This ensures failed attempts are visible in the dashboard
    for d in liveness_docs:
        ts = d.get("timestamp")
        uid = str(d.get("user_id")) if d.get("user_id") else None
        stage = d.get("stage") or "unknown"
        # CRITICAL: Properly map liveness stage to status
        # "passed" -> success, "failed" -> failed, everything else -> info
        if stage == "failed":
            status = "failed"
        elif stage == "passed":
            status = "success"
        else:
            status = "info"
        activity.append(
            DashboardActivityItem(
                id=str(d.get("_id")),
                timestamp=iso(ts),
                type="liveness",
                stage=stage,
                status=status,
                title="Liveness check",
                user_id=uid,
                user_name=user_name_by_id.get(uid) if uid else None,
                device_id=d.get("device_id"),
                session_id=d.get("session_id"),
            )
        )

    # Sort merged feed and keep last 10
    activity.sort(key=lambda x: x.timestamp, reverse=True)
    activity = activity[:10]

    return DashboardOverviewResponse(
        total_users=total_users,
        today_attendance_count=today_attendance_count,
        currently_checked_in_users=currently_checked_in_users,
        failed_recognition_today=failed_recognition_today,
        failed_liveness_today=failed_liveness_today,
        system_status=system_status,
        recent_activity=activity,
    )

# User Management Endpoints
@router.get("/users")
async def get_users(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    status: Optional[str] = None,
    role: Optional[str] = None,
    current_admin: AdminOut = Depends(get_current_admin),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Get all users with search and filtering"""
    users, total = await user_repo.get_all_users(
        skip=skip,
        limit=limit,
        search=search,
        access_level=role,
        status=status
    )
    
    # Convert to dict with enrollment status
    user_list = []
    for user in users:
        user_dict = user.model_dump(by_alias=True)
        user_dict["id"] = str(user_dict["_id"])
        del user_dict["_id"]
        
        # Determine enrollment status
        if not user.face_encodings or len(user.face_encodings) == 0:
            user_dict["enrollment_status"] = "not_enrolled"
        else:
            user_dict["enrollment_status"] = "enrolled"
        
        # Ensure status field exists
        if "status" not in user_dict:
            user_dict["status"] = "active"
        
        user_list.append(user_dict)
    
    return {"users": user_list, "total": total}

@router.get("/users/{user_id}")
async def get_user_by_id(
    user_id: str,
    current_admin: AdminOut = Depends(get_current_admin),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Get user by ID"""
    user = await user_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_dict = user.model_dump(by_alias=True)
    user_dict["id"] = str(user_dict["_id"])
    del user_dict["_id"]
    
    # Determine enrollment status
    if not user.face_encodings or len(user.face_encodings) == 0:
        user_dict["enrollment_status"] = "not_enrolled"
    else:
        user_dict["enrollment_status"] = "enrolled"
    
    # Ensure status field exists
    if "status" not in user_dict:
        user_dict["status"] = "active"
    
    return user_dict

@router.post("/users")
async def create_user(
    user_data: UserCreate,
    current_admin: AdminOut = Depends(require_admin_role),
    user_repo: UserRepository = Depends(get_user_repository),
    system_log_repo: SystemLogRepository = Depends(get_system_log_repository)
):
    """Create a new user"""
    # Check if employee_id already exists
    if await user_repo.check_employee_id_exists(user_data.employee_id):
        raise HTTPException(status_code=400, detail="Employee ID already exists")
    
    user = User(
        name=user_data.name,
        employee_id=user_data.employee_id,
        access_level=user_data.access_level,
        status="active",
        face_encodings=[]
    )
    
    created_user = await user_repo.add_user(user)
    
    # Log admin action
    await system_log_repo.add_log(SystemLog(
        type="admin_action",
        stage="created",
        admin_id=current_admin.id,
        action="create_user",
        target_user_id=str(created_user.id),
        metadata={"name": created_user.name, "employee_id": created_user.employee_id}
    ))
    
    user_dict = created_user.model_dump(by_alias=True)
    user_dict["id"] = str(user_dict["_id"])
    del user_dict["_id"]
    user_dict["enrollment_status"] = "not_enrolled"
    user_dict["status"] = "active"
    
    return user_dict

@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    user_data: UserUpdate,
    current_admin: AdminOut = Depends(require_admin_role),
    user_repo: UserRepository = Depends(get_user_repository),
    system_log_repo: SystemLogRepository = Depends(get_system_log_repository)
):
    """Update user information"""
    user = await user_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if employee_id already exists (excluding current user)
    if user_data.employee_id and user_data.employee_id != user.employee_id:
        if await user_repo.check_employee_id_exists(user_data.employee_id, exclude_user_id=user_id):
            raise HTTPException(status_code=400, detail="Employee ID already exists")
    
    # Prepare update data
    update_data = {}
    if user_data.name is not None:
        update_data["name"] = user_data.name
    if user_data.employee_id is not None:
        update_data["employee_id"] = user_data.employee_id
    if user_data.access_level is not None:
        update_data["access_level"] = user_data.access_level
    if user_data.status is not None:
        update_data["status"] = user_data.status
    
    if update_data:
        await user_repo.update_user(user_id, update_data)
    
    # Log admin action
    await system_log_repo.add_log(SystemLog(
        type="admin_action",
        stage="updated",
        admin_id=current_admin.id,
        action="update_user",
        target_user_id=user_id,
        metadata=update_data
    ))
    
    # Get updated user
    updated_user = await user_repo.get_user_by_id(user_id)
    user_dict = updated_user.model_dump(by_alias=True)
    user_dict["id"] = str(user_dict["_id"])
    del user_dict["_id"]
    
    # Determine enrollment status
    if not updated_user.face_encodings or len(updated_user.face_encodings) == 0:
        user_dict["enrollment_status"] = "not_enrolled"
    else:
        user_dict["enrollment_status"] = "enrolled"
    
    # Ensure status field exists
    if "status" not in user_dict:
        user_dict["status"] = "active"
    
    return user_dict

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_admin: AdminOut = Depends(require_admin_role),
    user_repo: UserRepository = Depends(get_user_repository),
    system_log_repo: SystemLogRepository = Depends(get_system_log_repository)
):
    """Delete a user"""
    user = await user_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    await user_repo.delete_user(user_id)
    
    # Log admin action
    await system_log_repo.add_log(SystemLog(
        type="admin_action",
        stage="deleted",
        admin_id=current_admin.id,
        action="delete_user",
        target_user_id=user_id,
        metadata={"name": user.name, "employee_id": user.employee_id}
    ))
    
    return {"message": "User deleted successfully"}

@router.get("/users/{user_id}/enrollment")
async def get_user_enrollment_status(
    user_id: str,
    current_admin: AdminOut = Depends(get_current_admin),
    user_repo: UserRepository = Depends(get_user_repository),
    system_log_repo: SystemLogRepository = Depends(get_system_log_repository)
):
    """Get user enrollment status and metadata"""
    user = await user_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get enrollment logs
    enrollment_logs = await system_log_repo.get_enrollment_logs_by_user(user_id, limit=10)
    
    # Determine enrollment status
    if not user.face_encodings or len(user.face_encodings) == 0:
        enrollment_status = "not_enrolled"
    else:
        enrollment_status = "enrolled"
    
    # Get enrollment metadata from logs
    enrollment_metadata = None
    if enrollment_logs:
        latest_log = enrollment_logs[0]
        enrollment_metadata = {
            "enrollment_date": latest_log.timestamp.isoformat() if latest_log.timestamp else None,
            "device_id": latest_log.device_id,
            "enrollment_attempts": len(enrollment_logs),
            "model_version": latest_log.model_version
        }
    
    return {
        "enrollment_status": enrollment_status,
        "enrollment_metadata": enrollment_metadata
    }

@router.post("/users/{user_id}/re-enroll")
async def force_re_enrollment(
    user_id: str,
    current_admin: AdminOut = Depends(require_admin_role),
    user_repo: UserRepository = Depends(get_user_repository),
    system_log_repo: SystemLogRepository = Depends(get_system_log_repository)
):
    """Force user re-enrollment by clearing face encodings"""
    user = await user_repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Clear face encodings
    await user_repo.update_user(user_id, {"face_encodings": []})
    
    # Log admin action
    await system_log_repo.add_log(SystemLog(
        type="admin_action",
        stage="reset",
        admin_id=current_admin.id,
        action="force_re_enrollment",
        target_user_id=user_id,
        metadata={"name": user.name, "employee_id": user.employee_id}
    ))
    
    return {"message": "User enrollment reset successfully. User must re-enroll."}

@router.post("/users/bulk-import")
async def bulk_import_users(
    file: UploadFile = File(...),
    current_admin: AdminOut = Depends(require_admin_role),
    user_repo: UserRepository = Depends(get_user_repository),
    system_log_repo: SystemLogRepository = Depends(get_system_log_repository)
):
    """Bulk import users from CSV file"""
    import csv
    import io
    
    # Read CSV file
    contents = await file.read()
    text_contents = contents.decode('utf-8')
    csv_reader = csv.DictReader(io.StringIO(text_contents))
    
    created_count = 0
    errors = []
    
    for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (header is row 1)
        try:
            name = row.get('name', '').strip()
            employee_id = row.get('employee_id', '').strip()
            access_level = row.get('access_level', 'employee').strip()
            
            if not name or not employee_id:
                errors.append(f"Row {row_num}: Name and Employee ID are required")
                continue
            
            # Check if employee_id already exists
            if await user_repo.check_employee_id_exists(employee_id):
                errors.append(f"Row {row_num}: Employee ID {employee_id} already exists")
                continue
            
            # Create user
            user = User(
                name=name,
                employee_id=employee_id,
                access_level=access_level,
                status="active",
                face_encodings=[]
            )
            
            created_user = await user_repo.add_user(user)
            
            # Log admin action
            await system_log_repo.add_log(SystemLog(
                type="admin_action",
                stage="created",
                admin_id=current_admin.id,
                action="bulk_import_user",
                target_user_id=str(created_user.id),
                metadata={"name": created_user.name, "employee_id": created_user.employee_id}
            ))
            
            created_count += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
    
    return {
        "message": f"Bulk import completed. {created_count} users created.",
        "created_count": created_count,
        "errors": errors if errors else None
    }

# Attendance Endpoints
@router.get("/attendance")
async def get_attendance_records(
    skip: int = 0,
    limit: int = 100,
    user_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    status: Optional[str] = None,
    current_admin: AdminOut = Depends(get_current_admin),
    attendance_repo: AttendanceRepository = Depends(get_attendance_repository),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Get all attendance records with filtering"""
    logs, total = await attendance_repo.get_all_logs(
        skip=skip,
        limit=limit,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        status=status
    )
    
    # Enrich with user names
    records = []
    for log in logs:
        record_dict = log.model_dump(by_alias=True)
        record_dict["id"] = str(record_dict["_id"])
        del record_dict["_id"]
        
        # Get user name
        if log.user_id:
            user = await user_repo.get_user_by_id(log.user_id)
            if user:
                record_dict["user_name"] = user.name
        
        # Add liveness_status (map from liveness field)
        record_dict["liveness_status"] = log.liveness
        
        # Add device_id and session_id (now part of model)
        record_dict["device_id"] = log.device_id if hasattr(log, "device_id") and log.device_id else None
        record_dict["session_id"] = log.session_id if hasattr(log, "session_id") and log.session_id else None
        
        records.append(record_dict)
    
    return {"records": records, "total": total}

@router.get("/attendance/{record_id}")
async def get_attendance_record_by_id(
    record_id: str,
    current_admin: AdminOut = Depends(get_current_admin),
    attendance_repo: AttendanceRepository = Depends(get_attendance_repository),
    user_repo: UserRepository = Depends(get_user_repository)
):
    """Get attendance record by ID"""
    log = await attendance_repo.get_log_by_id(record_id)
    if not log:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    
    record_dict = log.model_dump(by_alias=True)
    record_dict["id"] = str(record_dict["_id"])
    del record_dict["_id"]
    
    # Get user name
    if log.user_id:
        user = await user_repo.get_user_by_id(log.user_id)
        if user:
            record_dict["user_name"] = user.name
    
    # Add liveness_status (map from liveness field)
    record_dict["liveness_status"] = log.liveness
    
    # Add device_id and session_id if they exist (may not be in model)
    record_dict["device_id"] = getattr(log, "device_id", None)
    record_dict["session_id"] = getattr(log, "session_id", None)
    
    return record_dict

# Logs Endpoints
@router.get("/logs/enrollment")
async def get_enrollment_logs(
    user_id: Optional[str] = None,
    limit: int = 100,
    current_admin: AdminOut = Depends(get_current_admin),
    system_log_repo: SystemLogRepository = Depends(get_system_log_repository)
):
    """Get enrollment logs"""
    if user_id:
        logs = await system_log_repo.get_enrollment_logs_by_user(user_id, limit=limit)
    else:
        logs = await system_log_repo.get_enrollment_logs(limit=limit)
    
    return [log.model_dump(by_alias=True) for log in logs]

@router.get("/logs/recognition")
async def get_recognition_logs(
    session_id: Optional[str] = None,
    limit: int = 100,
    current_admin: AdminOut = Depends(get_current_admin),
    system_log_repo: SystemLogRepository = Depends(get_system_log_repository)
):
    """Get recognition logs"""
    if session_id:
        logs = await system_log_repo.get_recognition_logs_by_session(session_id, limit=limit)
    else:
        logs = await system_log_repo.get_recognition_logs(limit=limit)
    
    return [log.model_dump(by_alias=True) for log in logs]

@router.get("/logs/liveness")
async def get_liveness_logs(
    session_id: Optional[str] = None,
    limit: int = 100,
    current_admin: AdminOut = Depends(get_current_admin),
    system_log_repo: SystemLogRepository = Depends(get_system_log_repository)
):
    """Get liveness logs"""
    if session_id:
        logs = await system_log_repo.get_liveness_logs_by_session(session_id, limit=limit)
    else:
        logs = await system_log_repo.get_liveness_logs(limit=limit)
    
    return [log.model_dump(by_alias=True) for log in logs]

@router.get("/logs/admin-actions")
async def get_admin_action_logs(
    admin_id: Optional[str] = None,
    limit: int = 100,
    current_admin: AdminOut = Depends(get_current_admin),
    system_log_repo: SystemLogRepository = Depends(get_system_log_repository)
):
    """Get admin action logs"""
    if admin_id:
        logs = await system_log_repo.get_admin_action_logs_by_admin(admin_id, limit=limit)
    else:
        logs = await system_log_repo.get_admin_action_logs(limit=limit)
    
    return [log.model_dump(by_alias=True) for log in logs]

# Real-Time Attendance Feed WebSocket
@router.websocket("/ws/attendance-feed")
async def attendance_feed_websocket(websocket: WebSocket):
    """
    Real-time attendance feed WebSocket endpoint.
    Streams new attendance events as they occur.
    """
    from app.core.database import get_database
    from app.domains.admin.repository import AdminRepository
    
    # Get dependencies manually (WebSocket doesn't support Depends())
    db = get_database()
    if db is None:
        await websocket.close(code=1011, reason="Database not available")
        return
    
    attendance_repo = AttendanceRepository(db)
    user_repo = UserRepository(db)
    admin_repo = AdminRepository(db)
    admin_service = AdminService(admin_repo)
    
    # Authenticate via query parameter (WebSocket doesn't support headers easily)
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Authentication required")
        return
    
    # Verify token
    try:
        admin = await admin_service.get_current_admin(token)
        if not admin:
            await websocket.close(code=1008, reason="Invalid token")
            return
    except Exception as e:
        print(f"⚠️ WebSocket auth error: {e}")
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    await websocket.accept()
    
    # Track last seen timestamp to only send new events
    last_timestamp = datetime.now(timezone.utc) - timedelta(seconds=5)  # Start 5 seconds ago
    is_paused = False
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "message": "Real-time feed connected",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        while True:
            # Check for pause/resume commands from client
            try:
                # Set timeout to check for client messages
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                try:
                    command = json.loads(data)
                    if command.get("action") == "pause":
                        is_paused = True
                        await websocket.send_json({
                            "type": "paused",
                            "message": "Feed paused"
                        })
                        continue
                    elif command.get("action") == "resume":
                        is_paused = False
                        await websocket.send_json({
                            "type": "resumed",
                            "message": "Feed resumed"
                        })
                        # Update last_timestamp to avoid sending old events
                        last_timestamp = datetime.now(timezone.utc) - timedelta(seconds=2)
                        continue
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                pass  # No message from client, continue polling
            
            # If paused, skip polling
            if is_paused:
                await asyncio.sleep(1)
                continue
            
            # Poll for new attendance events
            try:
                # Ensure last_timestamp is timezone-aware for comparison
                from datetime import timezone as tz
                if last_timestamp.tzinfo is None:
                    last_timestamp = last_timestamp.replace(tzinfo=tz.utc)
                
                # Query for events after last_timestamp
                query = {
                    "timestamp": {"$gt": last_timestamp},
                    "liveness": {"$exists": True, "$ne": "pending"}
                }
                
                cursor = attendance_repo.collection.find(query).sort("timestamp", 1).limit(50)
                events = []
                
                async for doc in cursor:
                    doc["_id"] = str(doc["_id"])
                    if "liveness" not in doc or not doc["liveness"]:
                        continue
                    
                    # Ensure doc timestamp is timezone-aware for comparison
                    doc_timestamp = doc.get("timestamp")
                    if isinstance(doc_timestamp, datetime):
                        if doc_timestamp.tzinfo is None:
                            doc_timestamp = doc_timestamp.replace(tzinfo=tz.utc)
                        
                        # Only process if after last_timestamp
                        if doc_timestamp <= last_timestamp:
                            continue
                    
                    # Get user name
                    user_name = "Unknown"
                    if doc.get("user_id"):
                        user = await user_repo.get_user_by_id(doc["user_id"])
                        if user:
                            user_name = user.name
                    
                    # Format event
                    event = {
                        "id": doc["_id"],
                        "user_id": doc.get("user_id"),
                        "user_name": user_name,
                        "timestamp": doc_timestamp.isoformat() if isinstance(doc_timestamp, datetime) else str(doc_timestamp),
                        "status": "success" if doc.get("liveness") == "passed" else "failed",
                        "liveness": doc.get("liveness"),
                        "event_type": doc.get("event_type", "check_in"),
                        "device_id": doc.get("device_id"),
                        "session_id": doc.get("session_id")
                    }
                    events.append(event)
                    
                    # Update last_timestamp (ensure timezone-aware)
                    if isinstance(doc_timestamp, datetime):
                        if doc_timestamp > last_timestamp:
                            last_timestamp = doc_timestamp
                
                # Send events to client
                if events:
                    for event in events:
                        await websocket.send_json({
                            "type": "attendance_event",
                            "event": event
                        })
            
            except Exception as e:
                print(f"⚠️ Error polling attendance events: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"Error fetching events: {str(e)}"
                })
            
            # Wait before next poll (1 second interval)
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        print("🔌 Attendance feed WebSocket disconnected")
    except Exception as e:
        print(f"❌ Attendance feed WebSocket error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            await websocket.close()
        except:
            pass

# Notification Endpoints
@router.get("/notifications")
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    current_admin: AdminOut = Depends(get_current_admin),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Get notifications for current admin"""
    notifications = await notification_service.get_notifications(
        admin_id=current_admin.id,
        limit=limit,
        unread_only=unread_only
    )
    return [n.model_dump(by_alias=True) for n in notifications]

@router.get("/notifications/unread-count")
async def get_unread_count(
    current_admin: AdminOut = Depends(get_current_admin),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Get unread notification count"""
    count = await notification_service.get_unread_count(current_admin.id)
    return {"count": count}

@router.post("/notifications/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: str,
    current_admin: AdminOut = Depends(get_current_admin),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Mark a notification as read"""
    success = await notification_service.mark_as_read(notification_id, current_admin.id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"message": "Notification marked as read"}

@router.post("/notifications/mark-all-read")
async def mark_all_notifications_as_read(
    current_admin: AdminOut = Depends(get_current_admin),
    notification_service: NotificationService = Depends(get_notification_service)
):
    """Mark all notifications as read"""
    count = await notification_service.mark_all_as_read(current_admin.id)
    return {"message": f"{count} notifications marked as read", "count": count}

# Message Endpoints
class SendMessageRequest(BaseModel):
    title: str
    content: str
    message_type: MessageType = MessageType.INFO
    target_type: MessageTarget
    target_ids: List[str] = Field(default_factory=list)

@router.post("/messages/send")
async def send_message(
    request: SendMessageRequest,
    current_admin: AdminOut = Depends(require_admin_role),
    message_service: MessageService = Depends(get_message_service)
):
    """Send a message to users"""
    message = await message_service.send_message(
        sender_admin_id=current_admin.id,
        sender_name=current_admin.name,
        title=request.title,
        content=request.content,
        message_type=request.message_type,
        target_type=request.target_type,
        target_ids=request.target_ids
    )
    return message.model_dump(by_alias=True)

@router.get("/messages")
async def get_messages(
    limit: int = 50,
    current_admin: AdminOut = Depends(get_current_admin),
    message_service: MessageService = Depends(get_message_service)
):
    """Get messages sent by current admin"""
    messages = await message_service.get_messages_by_sender(current_admin.id, limit)
    return [m.model_dump(by_alias=True) for m in messages]

@router.get("/messages/{message_id}/delivery-status")
async def get_message_delivery_status(
    message_id: str,
    current_admin: AdminOut = Depends(get_current_admin),
    message_service: MessageService = Depends(get_message_service)
):
    """Get delivery status for a message"""
    status = await message_service.get_message_delivery_status(message_id)
    if not status:
        raise HTTPException(status_code=404, detail="Message not found")
    return status
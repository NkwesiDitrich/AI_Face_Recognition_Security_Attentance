from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
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
    security
)

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
        
        # Add liveness_status and device_id
        record_dict["liveness_status"] = log.liveness
        record_dict["device_id"] = log.device_id
        
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
    
    # Add liveness_status and device_id
    record_dict["liveness_status"] = log.liveness
    record_dict["device_id"] = log.device_id
    
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
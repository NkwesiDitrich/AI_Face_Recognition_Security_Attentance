from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.domains.user_portal.service import UserPortalService
from app.domains.user_portal.repository import UserPortalCredentialRepository, UserPortalLogRepository
from app.domains.user.repository import UserRepository
from app.domains.attendance.repository import AttendanceRepository
from app.domains.notification.repository import MessageRepository
from app.core.database import get_database
from motor.motor_asyncio import AsyncIOMotorDatabase
from jose import jwt, JWTError
from datetime import timezone

# JWT Configuration (same as admin service)
# For production, use environment variable: SECRET_KEY = os.getenv("JWT_SECRET_KEY", "...")
SECRET_KEY = "QL1MGjc63ApIDktA3DxzVE-vNk_jT3zFKgJQmcAWyeo"
ALGORITHM = "HS256"

router = APIRouter(prefix="/user-portal", tags=["User Portal"])
security = HTTPBearer()

# Dependency functions
def get_user_portal_credential_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> UserPortalCredentialRepository:
    return UserPortalCredentialRepository(db)

def get_user_portal_log_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> UserPortalLogRepository:
    return UserPortalLogRepository(db)

def get_user_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> UserRepository:
    return UserRepository(db)

def get_attendance_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> AttendanceRepository:
    return AttendanceRepository(db)

def get_message_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> MessageRepository:
    return MessageRepository(db)

def get_user_portal_service(
    credential_repo: UserPortalCredentialRepository = Depends(get_user_portal_credential_repo),
    log_repo: UserPortalLogRepository = Depends(get_user_portal_log_repo),
    user_repo: UserRepository = Depends(get_user_repo),
    attendance_repo: AttendanceRepository = Depends(get_attendance_repo),
    message_repo: MessageRepository = Depends(get_message_repo)
) -> UserPortalService:
    # NotificationRepository not needed for user portal service
    from app.domains.notification.repository import NotificationRepository
    db = get_database()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    notification_repo = NotificationRepository(db)
    return UserPortalService(credential_repo, log_repo, user_repo, attendance_repo, message_repo, notification_repo)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_portal_service: UserPortalService = Depends(get_user_portal_service)
):
    """Get current authenticated user from JWT token"""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "user_portal":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# Request/Response models
class SetupPasswordRequest(BaseModel):
    user_id: str
    password: str
    confirm_password: str

class LoginRequest(BaseModel):
    user_id: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str

class CheckUserRequest(BaseModel):
    user_id: str

# Endpoints
@router.post("/check-user")
async def check_user(
    request: CheckUserRequest,
    user_portal_service: UserPortalService = Depends(get_user_portal_service)
):
    """Check if user exists and if password is set - accepts employee_id or MongoDB _id"""
    from app.domains.user.repository import UserRepository
    from app.core.database import get_database
    from app.domains.user_portal.repository import UserPortalCredentialRepository
    
    db = get_database()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    
    user_repo = UserRepository(db)
    credential_repo = UserPortalCredentialRepository(db)
    
    # Check if user exists (search by employee_id or _id)
    user = await user_repo.get_user_by_id_or_employee_id(request.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not active"
        )
    
    # Check if password is set (use actual MongoDB _id)
    actual_user_id = str(user.id)
    credential = await credential_repo.get_by_user_id(actual_user_id)
    password_set = credential is not None
    
    return {
        "user_exists": True,
        "password_set": password_set,
        "user_name": user.name,
        "employee_id": user.employee_id,
        "user_id": actual_user_id  # Return actual MongoDB _id for frontend use
    }

@router.post("/setup-password")
async def setup_password(
    request: SetupPasswordRequest,
    req: Request,
    user_portal_service: UserPortalService = Depends(get_user_portal_service)
):
    """Setup password for first-time login"""
    if request.password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Passwords do not match"
        )
    
    # Get client IP and user agent from request
    client_ip = req.client.host if req.client else None
    user_agent = req.headers.get("user-agent")
    
    result = await user_portal_service.setup_password(
        request.user_id,
        request.password,
        ip_address=client_ip,
        user_agent=user_agent
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=result["message"]
        )
    
    return {"message": result["message"], "success": True}

@router.post("/login")
async def login(
    request: LoginRequest,
    req: Request,
    user_portal_service: UserPortalService = Depends(get_user_portal_service)
):
    """Login user"""
    # Get client IP and user agent
    client_ip = req.client.host if req.client else None
    user_agent = req.headers.get("user-agent")
    
    result = await user_portal_service.login(
        request.user_id,
        request.password,
        ip_address=client_ip,
        user_agent=user_agent
    )
    
    if not result["success"]:
        # If password not set, return 400 (Bad Request) instead of 401 (Unauthorized)
        # This helps frontend distinguish between "password not set" and "invalid password"
        if "Password not set" in result["message"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["message"]
            )
        # For invalid credentials or user not found, return 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result["message"]
        )
    
    return result

@router.get("/profile")
async def get_profile(
    user_id: str = Depends(get_current_user),
    user_portal_service: UserPortalService = Depends(get_user_portal_service)
):
    """Get user profile"""
    profile = await user_portal_service.get_user_profile(user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile

@router.get("/attendance")
async def get_attendance(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    user_id: str = Depends(get_current_user),
    user_portal_service: UserPortalService = Depends(get_user_portal_service)
):
    """Get user attendance history - accepts date strings (yyyy-MM-dd) or ISO datetime strings"""
    from datetime import timezone
    
    start_dt = None
    end_dt = None
    
    if start_date:
        try:
            # Try parsing as date string (yyyy-MM-dd)
            if len(start_date) == 10 and '-' in start_date:
                # Date string like "2024-01-15" - set to start of day UTC
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                start_dt = start_dt.replace(hour=0, minute=0, second=0, tzinfo=timezone.utc)
            else:
                # Try ISO format
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
        except Exception as e:
            print(f"⚠️ Error parsing start_date '{start_date}': {e}")
            pass
    
    if end_date:
        try:
            # Try parsing as date string (yyyy-MM-dd)
            if len(end_date) == 10 and '-' in end_date:
                # Date string like "2024-01-15" - set to end of day UTC
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                end_dt = end_dt.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
            else:
                # Try ISO format
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
        except Exception as e:
            print(f"⚠️ Error parsing end_date '{end_date}': {e}")
            pass
    
    attendance = await user_portal_service.get_user_attendance(
        user_id,
        start_date=start_dt,
        end_date=end_dt,
        limit=limit
    )
    return {"attendance": attendance}

@router.get("/messages")
async def get_messages(
    limit: int = 50,
    user_id: str = Depends(get_current_user),
    user_portal_service: UserPortalService = Depends(get_user_portal_service)
):
    """Get messages for user"""
    messages = await user_portal_service.get_user_messages(user_id, limit)
    return {"messages": messages}

@router.post("/messages/{message_id}/read")
async def mark_message_as_read(
    message_id: str,
    user_id: str = Depends(get_current_user),
    user_portal_service: UserPortalService = Depends(get_user_portal_service)
):
    """Mark a message as read"""
    success = await user_portal_service.mark_message_as_read(message_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"message": "Message marked as read"}

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    req: Request,
    user_id: str = Depends(get_current_user),
    user_portal_service: UserPortalService = Depends(get_user_portal_service)
):
    """Change user password"""
    if request.new_password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    
    client_ip = req.client.host if req.client else None
    user_agent = req.headers.get("user-agent")
    
    result = await user_portal_service.change_password(
        user_id,
        request.old_password,
        request.new_password,
        ip_address=client_ip,
        user_agent=user_agent
    )
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return {"message": result["message"]}

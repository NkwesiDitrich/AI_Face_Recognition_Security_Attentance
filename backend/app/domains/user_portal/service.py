from typing import Optional
import bcrypt
import hashlib
from app.domains.user_portal.models import UserPortalCredential, UserPortalLog
from app.domains.user_portal.repository import UserPortalCredentialRepository, UserPortalLogRepository
from app.domains.user.repository import UserRepository
from app.domains.attendance.repository import AttendanceRepository
from app.domains.notification.repository import MessageRepository, NotificationRepository
from datetime import datetime, timezone
from jose import jwt

# JWT Configuration (same as admin service)
# For production, use environment variable: SECRET_KEY = os.getenv("JWT_SECRET_KEY", "...")
SECRET_KEY = "QL1MGjc63ApIDktA3DxzVE-vNk_jT3zFKgJQmcAWyeo"
ALGORITHM = "HS256"

class UserPortalService:
    """Service for user portal operations"""
    
    def __init__(
        self,
        credential_repo: UserPortalCredentialRepository,
        log_repo: UserPortalLogRepository,
        user_repo: UserRepository,
        attendance_repo: AttendanceRepository,
        message_repo: MessageRepository,
        notification_repo: Optional[NotificationRepository] = None
    ):
        self.credential_repo = credential_repo
        self.log_repo = log_repo
        self.user_repo = user_repo
        self.attendance_repo = attendance_repo
        self.message_repo = message_repo
        self.notification_repo = notification_repo
    
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt (handles 72-byte limit automatically)"""
        # bcrypt has a 72-byte limit, but utf-8 encoding handles truncation naturally
        # For safety, we encode to bytes first
        password_bytes = password.encode('utf-8')
        # If password is too long, hash it first to reduce size (sha256 is 32 bytes)
        if len(password_bytes) > 72:
            password_bytes = hashlib.sha256(password_bytes).digest()
        # Hash with bcrypt
        hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
        return hashed.decode('utf-8')
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against the hash"""
        try:
            password_bytes = plain_password.encode('utf-8')
            # If password is too long, hash it first (same as in hash_password)
            if len(password_bytes) > 72:
                password_bytes = hashlib.sha256(password_bytes).digest()
            # Verify with bcrypt
            return bcrypt.checkpw(password_bytes, hashed_password.encode('utf-8'))
        except Exception:
            return False
    
    async def setup_password(
        self,
        user_id: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> dict:
        """Setup password for first-time login"""
        # Check if user exists and is active (search by employee_id or _id)
        user = await self.user_repo.get_user_by_id_or_employee_id(user_id)
        if not user:
            await self.log_repo.create_log(UserPortalLog(
                user_id=user_id,
                action="password_setup",
                success=False,
                error_message="User not found",
                ip_address=ip_address,
                user_agent=user_agent
            ))
            return {"success": False, "message": "User not found"}
        
        # Get actual MongoDB _id from user object
        actual_user_id = str(user.id)
        
        if user.status != "active":
            await self.log_repo.create_log(UserPortalLog(
                user_id=actual_user_id,
                action="password_setup",
                success=False,
                error_message="User is not active",
                ip_address=ip_address,
                user_agent=user_agent
            ))
            return {"success": False, "message": "User account is not active"}
        
        # Check if credentials already exist (use actual MongoDB _id)
        existing = await self.credential_repo.get_by_user_id(actual_user_id)
        if existing:
            await self.log_repo.create_log(UserPortalLog(
                user_id=actual_user_id,
                action="password_setup",
                success=False,
                error_message="Password already set",
                ip_address=ip_address,
                user_agent=user_agent
            ))
            return {"success": False, "message": "Password already set. Please login."}
        
        # Validate password
        if len(password) < 8:
            return {"success": False, "message": "Password must be at least 8 characters"}
        
        # Hash and save password (use actual MongoDB _id)
        password_hash = self.hash_password(password)
        credential = UserPortalCredential(
            user_id=actual_user_id,  # Store MongoDB _id, not employee_id
            password_hash=password_hash
        )
        await self.credential_repo.create_credential(credential)
        
        # Log success
        await self.log_repo.create_log(UserPortalLog(
            user_id=actual_user_id,
            action="password_setup",
            success=True,
            ip_address=ip_address,
            user_agent=user_agent
        ))
        
        return {"success": True, "message": "Password set successfully"}
    
    async def login(
        self,
        user_id: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> dict:
        """Login user - accepts either employee_id or MongoDB _id"""
        # Check if user exists and is active (search by employee_id or _id)
        user = await self.user_repo.get_user_by_id_or_employee_id(user_id)
        if not user:
            await self.log_repo.create_log(UserPortalLog(
                user_id=user_id,
                action="login",
                success=False,
                error_message="User not found",
                ip_address=ip_address,
                user_agent=user_agent
            ))
            return {"success": False, "message": "Invalid credentials"}
        
        # Get actual MongoDB _id from user object
        actual_user_id = str(user.id)
        
        if user.status != "active":
            await self.log_repo.create_log(UserPortalLog(
                user_id=actual_user_id,
                action="login",
                success=False,
                error_message="User is not active",
                ip_address=ip_address,
                user_agent=user_agent
            ))
            return {"success": False, "message": "User account is not active"}
        
        # Get credentials (use actual MongoDB _id)
        credential = await self.credential_repo.get_by_user_id(actual_user_id)
        if not credential:
            await self.log_repo.create_log(UserPortalLog(
                user_id=actual_user_id,
                action="login",
                success=False,
                error_message="Password not set",
                ip_address=ip_address,
                user_agent=user_agent
            ))
            return {"success": False, "message": "Password not set. Please setup password first."}
        
        # Verify password
        if not self.verify_password(password, credential.password_hash):
            await self.log_repo.create_log(UserPortalLog(
                user_id=actual_user_id,
                action="login",
                success=False,
                error_message="Invalid password",
                ip_address=ip_address,
                user_agent=user_agent
            ))
            return {"success": False, "message": "Invalid credentials"}
        
        # Update last login (use actual MongoDB _id)
        await self.credential_repo.update_last_login(actual_user_id)
        
        # Generate JWT token
        token = jwt.encode(
            {
                "user_id": str(user.id),
                "employee_id": user.employee_id,
                "type": "user_portal",
                "exp": datetime.now(timezone.utc).timestamp() + (24 * 60 * 60)  # 24 hours
            },
            SECRET_KEY,
            algorithm=ALGORITHM
        )
        
        # Log success
        await self.log_repo.create_log(UserPortalLog(
            user_id=actual_user_id,
            action="login",
            success=True,
            ip_address=ip_address,
            user_agent=user_agent
        ))
        
        return {
            "success": True,
            "token": token,
            "user": {
                "id": str(user.id),
                "name": user.name,
                "employee_id": user.employee_id,
                "access_level": user.access_level
            }
        }
    
    async def change_password(
        self,
        user_id: str,
        old_password: str,
        new_password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> dict:
        """Change user password"""
        # Get credentials
        credential = await self.credential_repo.get_by_user_id(user_id)
        if not credential:
            return {"success": False, "message": "Password not set"}
        
        # Verify old password
        if not self.verify_password(old_password, credential.password_hash):
            await self.log_repo.create_log(UserPortalLog(
                user_id=user_id,
                action="password_change",
                success=False,
                error_message="Invalid old password",
                ip_address=ip_address,
                user_agent=user_agent
            ))
            return {"success": False, "message": "Invalid old password"}
        
        # Validate new password
        if len(new_password) < 8:
            return {"success": False, "message": "Password must be at least 8 characters"}
        
        # Update password
        new_hash = self.hash_password(new_password)
        await self.credential_repo.update_password(user_id, new_hash)
        
        # Log success
        await self.log_repo.create_log(UserPortalLog(
            user_id=user_id,
            action="password_change",
            success=True,
            ip_address=ip_address,
            user_agent=user_agent
        ))
        
        return {"success": True, "message": "Password changed successfully"}
    
    async def get_user_profile(self, user_id: str) -> Optional[dict]:
        """Get user profile - accepts MongoDB _id"""
        user = await self.user_repo.get_user_by_id(user_id)
        if not user:
            return None
        
        # Check enrollment status
        enrollment_status = "not_enrolled"
        if user.face_encodings and len(user.face_encodings) > 0:
            enrollment_status = "enrolled"
        
        return {
            "id": str(user.id),
            "name": user.name,
            "employee_id": user.employee_id,
            "access_level": user.access_level,
            "status": user.status,
            "enrollment_status": enrollment_status
        }
    
    async def get_user_attendance(
        self,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> list:
        """Get user attendance history"""
        logs = await self.attendance_repo.get_logs_by_user(
            user_id, 
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        # Format for frontend
        attendance_list = []
        for log in logs:
            attendance_list.append({
                "id": str(log.id),
                "date": log.timestamp.date().isoformat(),
                "check_in_time": log.timestamp.isoformat() if log.event_type == "check_in" else None,
                "check_out_time": log.timestamp.isoformat() if log.event_type == "check_out" else None,
                "status": "present" if log.liveness == "passed" else "failed",
                "event_type": log.event_type
            })
        
        return attendance_list
    
    async def get_user_messages(self, user_id: str, limit: int = 50) -> list:
        """Get messages sent to user"""
        # Query delivery collection directly
        cursor = self.message_repo.delivery_collection.find({
            "user_id": user_id
        }).sort("created_at", -1).limit(limit)
        
        deliveries = []
        async for doc in cursor:
            deliveries.append(doc)
        
        messages = []
        for delivery in deliveries:
            message_id = delivery.get("message_id")
            if message_id:
                message = await self.message_repo.get_message_by_id(message_id)
                if message:
                    read_at = delivery.get("read_at")
                    if isinstance(read_at, datetime):
                        read_at_str = read_at.isoformat()
                    else:
                        read_at_str = None
                    
                    messages.append({
                        "id": str(message.id),
                        "title": message.title,
                        "content": message.content,
                        "message_type": message.message_type,
                        "sender_name": message.sender_name,
                        "created_at": message.created_at.isoformat(),
                        "read": delivery.get("read", False),
                        "read_at": read_at_str
                    })
        
        return messages
    
    async def mark_message_as_read(self, message_id: str, user_id: str) -> bool:
        """Mark a message as read and update message stats"""
        success = await self.message_repo.mark_delivery_as_read(message_id, user_id)
        if success:
            # Update message stats (delivered_count, read_count)
            await self.message_repo.update_message_stats(message_id)
        return success

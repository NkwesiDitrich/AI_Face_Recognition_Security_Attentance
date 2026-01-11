"""
Admin Service
Business logic for admin operations
"""

from typing import Optional
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import HTTPException, status
from app.domains.admin.models import Admin, AdminCreate, AdminOut
from app.domains.admin.repository import AdminRepository

# JWT Configuration
SECRET_KEY = "your-secret-key-change-this-in-production"  # TODO: Move to environment variable
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30 days


class AdminService:
    """Service for admin operations"""
    
    def __init__(self, admin_repo: AdminRepository):
        self.admin_repo = admin_repo
    
    def create_access_token(self, admin_id: str, email: str, role: str) -> str:
        """Create JWT access token"""
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode = {
            "sub": admin_id,
            "email": email,
            "role": role,
            "exp": expire
        }
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def verify_token(self, token: str) -> dict:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    async def authenticate(self, email: str, password: str) -> tuple[str, AdminOut]:
        """Authenticate admin and return token + admin data"""
        import logging
        logger = logging.getLogger(__name__)
        
        admin = await self.admin_repo.find_by_email(email)
        
        if not admin:
            logger.warning(f"Login attempt with non-existent email: {email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        if not admin.is_active:
            logger.warning(f"Login attempt for inactive admin: {email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin account is inactive"
            )
        
        # Debug: Check password_hash format
        try:
            password_valid = admin.verify_password(password)
            if not password_valid:
                logger.warning(f"Password verification failed for admin: {email}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password"
                )
        except Exception as e:
            logger.error(f"Error verifying password for admin {email}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        # Update last login
        await self.admin_repo.update_last_login(admin.id)
        
        # Create token
        token = self.create_access_token(admin.id, admin.email, admin.role)
        
        # Return admin data (without password)
        admin_out = AdminOut(
            id=admin.id,
            email=admin.email,
            name=admin.name,
            role=admin.role,
            is_active=admin.is_active,
            created_at=admin.created_at,
            last_login_at=datetime.utcnow()
        )
        
        return token, admin_out
    
    async def get_current_admin(self, token: str) -> AdminOut:
        """Get current admin from token"""
        payload = self.verify_token(token)
        admin_id = payload.get("sub")
        
        if not admin_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        admin = await self.admin_repo.find_by_id(admin_id)
        
        if not admin:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Admin not found"
            )
        
        if not admin.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin account is inactive"
            )
        
        return AdminOut(
            id=admin.id,
            email=admin.email,
            name=admin.name,
            role=admin.role,
            is_active=admin.is_active,
            created_at=admin.created_at,
            last_login_at=admin.last_login_at
        )
    
    async def create_admin(self, admin_data: AdminCreate) -> AdminOut:
        """Create a new admin (super admin only)"""
        # Check if email already exists
        existing = await self.admin_repo.find_by_email(admin_data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Create admin
        admin = Admin(
            email=admin_data.email,
            name=admin_data.name,
            password_hash=Admin.hash_password(admin_data.password),
            role=admin_data.role,
            is_active=True
        )
        
        created = await self.admin_repo.create(admin)
        
        return AdminOut(
            id=created.id,
            email=created.email,
            name=created.name,
            role=created.role,
            is_active=created.is_active,
            created_at=created.created_at,
            last_login_at=created.last_login_at
        )
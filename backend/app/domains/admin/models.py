"""
Admin Domain Model
Represents an admin user in the system
"""

from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, Any
from datetime import datetime
from bson import ObjectId
import bcrypt


class Admin(BaseModel):
    """
    Admin domain model - represents an admin user
    """
    
    id: Optional[Any] = Field(default=None, alias="_id")
    email: EmailStr = Field(..., description="Admin email address")
    name: str = Field(..., min_length=1, description="Admin full name")
    password_hash: str = Field(..., description="Hashed password")
    role: str = Field(default="admin", description="Admin role: super_admin, admin, viewer")
    is_active: bool = Field(default=True, description="Whether admin account is active")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login_at: Optional[datetime] = None
    
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str, datetime: lambda dt: dt.isoformat()},
    )
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def verify_password(self, password: str) -> bool:
        """Verify a password against the hash"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def model_dump(self, **kwargs):
        """Exclude password_hash from output"""
        if "exclude_none" not in kwargs:
            kwargs["exclude_none"] = True
        if "exclude" not in kwargs:
            kwargs["exclude"] = {"password_hash"}
        return super().model_dump(**kwargs)


class AdminCreate(BaseModel):
    """Schema for creating a new admin"""
    email: EmailStr
    name: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)
    role: str = Field(default="admin")


class AdminOut(BaseModel):
    """Schema for admin response (output)"""
    id: str
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    
    model_config = ConfigDict(
        json_encoders={ObjectId: str, datetime: lambda dt: dt.isoformat()},
    )
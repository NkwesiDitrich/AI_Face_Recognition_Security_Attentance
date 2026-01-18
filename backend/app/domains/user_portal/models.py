from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId

class UserPortalCredential(BaseModel):
    """User portal login credentials"""
    
    id: Optional[str] = Field(alias="_id", default=None)
    user_id: str = Field(..., description="User ID")
    password_hash: str = Field(..., description="Hashed password")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = Field(default=None, description="Last login timestamp")
    
    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}

class UserPortalLog(BaseModel):
    """Log for user portal activities (login, password setup, etc.)"""
    
    id: Optional[str] = Field(alias="_id", default=None)
    user_id: str = Field(..., description="User ID")
    action: str = Field(..., description="Action: login, password_setup, password_change, etc.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ip_address: Optional[str] = Field(default=None, description="IP address")
    user_agent: Optional[str] = Field(default=None, description="User agent")
    success: bool = Field(default=True, description="Whether action was successful")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    metadata: Optional[dict] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}

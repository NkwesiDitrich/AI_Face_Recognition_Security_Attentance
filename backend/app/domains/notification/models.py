from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum

class NotificationPriority(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class NotificationCategory(str, Enum):
    SYSTEM_ERROR = "system_error"
    LIVENESS_FAILURE = "liveness_failure"
    MISSED_ATTENDANCE = "missed_attendance"
    SUSPICIOUS_BEHAVIOR = "suspicious_behavior"
    ADMIN_ACTION = "admin_action"

class Notification(BaseModel):
    """Notification model for admin dashboard"""
    
    id: Optional[str] = Field(alias="_id", default=None)
    
    # Admin who receives the notification
    admin_id: str = Field(..., description="Admin ID who receives this notification")
    
    # Notification content
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification message")
    
    # Metadata
    priority: NotificationPriority = Field(default=NotificationPriority.INFO)
    category: NotificationCategory = Field(..., description="Notification category")
    
    # State
    is_read: bool = Field(default=False, description="Whether notification is read")
    read_at: Optional[datetime] = Field(default=None, description="When notification was read")
    
    # Source information
    source: Optional[str] = Field(default=None, description="Source of notification (e.g., 'system', 'admin_action')")
    source_id: Optional[str] = Field(default=None, description="ID of source entity (e.g., user_id, session_id)")
    
    # Timestamp
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Additional metadata
    metadata: Optional[dict] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}

class MessageType(str, Enum):
    INFO = "info"
    WARNING = "warning"
    INSTRUCTION = "instruction"

class MessageTarget(str, Enum):
    ALL_USERS = "all_users"
    GROUP = "group"
    SINGLE_USER = "single_user"

class Message(BaseModel):
    """Message model for sending messages to users"""
    
    id: Optional[str] = Field(alias="_id", default=None)
    
    # Message content
    title: str = Field(..., description="Message title")
    content: str = Field(..., description="Message content")
    message_type: MessageType = Field(default=MessageType.INFO)
    
    # Target
    target_type: MessageTarget = Field(..., description="Target type")
    target_ids: List[str] = Field(default_factory=list, description="Target IDs (user_ids or group names)")
    
    # Sender
    sender_admin_id: str = Field(..., description="Admin who sent the message")
    sender_name: Optional[str] = Field(default=None, description="Sender admin name")
    
    # Delivery tracking
    total_recipients: int = Field(default=0, description="Total number of recipients")
    delivered_count: int = Field(default=0, description="Number of delivered messages")
    read_count: int = Field(default=0, description="Number of read messages")
    
    # Timestamp
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scheduled_at: Optional[datetime] = Field(default=None, description="Scheduled send time (if None, send immediately)")
    sent_at: Optional[datetime] = Field(default=None, description="When message was actually sent")
    
    # Status
    status: str = Field(default="pending", description="Status: pending, sent, failed")
    
    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}

class MessageDelivery(BaseModel):
    """Message delivery tracking for individual users"""
    
    id: Optional[str] = Field(alias="_id", default=None)
    
    message_id: str = Field(..., description="Message ID")
    user_id: str = Field(..., description="User ID who received the message")
    
    # Delivery status
    delivered: bool = Field(default=False, description="Whether message was delivered")
    delivered_at: Optional[datetime] = Field(default=None, description="When message was delivered")
    
    read: bool = Field(default=False, description="Whether message was read")
    read_at: Optional[datetime] = Field(default=None, description="When message was read")
    
    # Timestamp
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}

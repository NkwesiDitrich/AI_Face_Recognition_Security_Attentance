from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class SystemLog(BaseModel):
    """
    Comprehensive system log for admin dashboard analytics.
    Follows professional attendance system logging standards.
    """
    
    # MongoDB ID
    id: Optional[str] = Field(alias="_id", default=None)
    
    # Log type: "face_enrollment", "attendance_recognition", "liveness", "attendance_record", "admin_action"
    type: str = Field(..., description="Type of log entry")
    
    # Stage: varies by type
    # For enrollment: "started", "completed", "reset", "failed"
    # For recognition: "started", "success", "failed"
    # For liveness: "started", "attempt", "passed", "failed"
    # For attendance_record: "created"
    # For admin_action: action name
    stage: str = Field(..., description="Stage of the process")
    
    # Timestamp
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Common fields (optional, context-dependent)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    device_id: Optional[str] = None
    
    # Enrollment-specific fields
    initiated_by: Optional[str] = None  # "admin" or "mobile_app"
    embedding_size: Optional[int] = None
    model_version: Optional[str] = None
    duration_ms: Optional[int] = None
    reason: Optional[str] = None  # For enrollment reset/failure
    admin_id: Optional[str] = None  # For enrollment reset or admin actions
    
    # Recognition-specific fields
    confidence: Optional[float] = None
    distance: Optional[float] = None
    
    # Liveness-specific fields
    actions_requested: Optional[List[str]] = None  # ["blink", "smile", etc.]
    attempt_number: Optional[int] = None
    failed_action: Optional[str] = None
    attempts_used: Optional[int] = None
    final_failed_action: Optional[str] = None
    
    # Attendance record specific
    event_type: Optional[str] = None  # "check_in", "check_out"
    liveness_status: Optional[str] = None  # "passed", "failed"
    total_duration_ms: Optional[int] = None
    
    # Admin action specific
    action: Optional[str] = None
    target_user_id: Optional[str] = None
    
    # Additional metadata (flexible)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda dt: dt.isoformat()}

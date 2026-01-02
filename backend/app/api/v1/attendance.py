# backend/app/api/v1/attendance.py
# ✅ FIXED - Proper liveness recording

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel
from app.domains.attendance.service import AttendanceService
from app.dependencies import get_attendance_service

router = APIRouter()

class AttendanceRecordRequest(BaseModel):
    user_id: str
    liveness: str = "passed"
    event_type: str = "check_in"

@router.websocket("/ws/attendance")
async def websocket_endpoint(websocket: WebSocket, attendance_service: AttendanceService = Depends(get_attendance_service)):
    await websocket.accept()
    try:
        while True:
            image_data = await websocket.receive_bytes()
            result = await attendance_service.process_attendance_frame(image_data)
            await websocket.send_json(result)
    except WebSocketDisconnect:
        pass

@router.post("/record")
async def record_attendance(
    request: AttendanceRecordRequest, 
    attendance_service: AttendanceService = Depends(get_attendance_service)
):
    """
    Record attendance after successful liveness detection.
    
    Expected from frontend:
    {
        "user_id": "abc123",
        "liveness": "passed",
        "event_type": "check_in"
    }
    """
    print(f"\n📝 Recording attendance for user: {request.user_id}")
    print(f"   Liveness: {request.liveness}")
    print(f"   Event: {request.event_type}")
    
    return await attendance_service.record_attendance(
        user_id=request.user_id,
        liveness_status=request.liveness,
        event_type=request.event_type
    )

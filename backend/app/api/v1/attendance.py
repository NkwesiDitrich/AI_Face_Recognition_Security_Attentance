# backend/app/api/v1/attendance.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from pydantic import BaseModel
from app.domains.attendance.service import AttendanceService
from app.dependencies import get_attendance_service

router = APIRouter()

class AttendanceRecordRequest(BaseModel):
    user_id: str
    liveness: str = "passed"
    event_type: str = "check_in"
    session_id: str

@router.websocket("/ws/attendance")
async def websocket_endpoint(websocket: WebSocket, attendance_service: AttendanceService = Depends(get_attendance_service)):
    await websocket.accept()
    try:
        while True:
            image_data = await websocket.receive_bytes()
            result = await attendance_service.process_attendance_frame(image_data)
            await websocket.send_json(result)
    except WebSocketDisconnect: pass

@router.post("/record")
async def record_attendance(request: AttendanceRecordRequest, attendance_service: AttendanceService = Depends(get_attendance_service)):
    return await attendance_service.record_attendance(
        user_id=request.user_id, 
        liveness_status=request.liveness, 
        event_type=request.event_type
    )
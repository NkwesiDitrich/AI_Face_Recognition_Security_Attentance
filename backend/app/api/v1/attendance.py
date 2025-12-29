# backend/app/api/v1/attendance.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Body
from app.domains.attendance.service import AttendanceService
from app.dependencies import get_attendance_service

router = APIRouter()

@router.websocket("/ws/attendance")
async def websocket_endpoint(websocket: WebSocket, service: AttendanceService = Depends(get_attendance_service)):
    await websocket.accept()
    print("DEBUG: WebSocket Connected")
    try:
        while True:
            image_data = await websocket.receive_bytes()
            result = await service.process_attendance_frame(image_data)
            print(f"DEBUG: Result -> {result['status']}")
            await websocket.send_json(result)
    except WebSocketDisconnect:
        print("DEBUG: WebSocket Disconnected")

@router.post("/record")
async def record_attendance(user_id: str = Body(..., embed=True), service: AttendanceService = Depends(get_attendance_service)):
    return await service.record_attendance(user_id)
# backend/app/api/v1/attendance.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Body
from app.domains.attendance.service import AttendanceService
from app.dependencies import get_attendance_service

router = APIRouter()

@router.websocket("/ws/attendance")
async def websocket_endpoint(
    websocket: WebSocket,
    attendance_service: AttendanceService = Depends(get_attendance_service)
):
    await websocket.accept()
    print("DEBUG: WebSocket connection established for attendance.")

    try:
        while True:
            # Receive image bytes from Flutter
            image_data = await websocket.receive_bytes()

            # Process the frame (Phase 1: Recognition)
            result = await attendance_service.process_attendance_frame(image_data)
            
            # Log result for debugging
            if result['status'] != 'processing':
                print(f"DEBUG: Frame Result -> {result['status']} ({result['message']})")

            # Send result back
            await websocket.send_json(result)

    except WebSocketDisconnect:
        print("DEBUG: Attendance WebSocket disconnected.")
    except Exception as e:
        print(f"DEBUG: WebSocket Error: {e}")

@router.post("/record")
async def record_attendance(
    user_id: str = Body(..., embed=True),
    attendance_service: AttendanceService = Depends(get_attendance_service)
):
    """
    Phase 5: Record attendance after successful liveness check.
    """
    print(f"DEBUG: Recording attendance for user_id: {user_id}")
    return await attendance_service.record_attendance(user_id)
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.domains.attendance.service import AttendanceService
from app.dependencies import get_attendance_service

router = APIRouter()

@router.websocket("/ws/attendance")
async def websocket_endpoint(
    websocket: WebSocket,
    attendance_service: AttendanceService = Depends(get_attendance_service)
):
    await websocket.accept()
    print("WebSocket connection established for attendance.")

    try:
        while True:
            # Receive image bytes from Flutter
            image_data = await websocket.receive_bytes()

            # Process the frame
            log_entry = await attendance_service.process_attendance_frame(image_data)

            # Send result back
            await websocket.send_json(log_entry)

    except WebSocketDisconnect:
        print("Attendance WebSocket disconnected.")
    except Exception as e:
        print(f"WebSocket Error: {e}")

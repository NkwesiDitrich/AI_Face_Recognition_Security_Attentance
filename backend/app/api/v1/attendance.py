# backend/app/api/v1/attendance.py
# ✅ FIXED - Safe response handling

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
    print("\n" + "="*50)
    print("🔌 WebSocket connection established for attendance")
    print("="*50)

    try:
        while True:
            # Receive image bytes from Flutter
            image_data = await websocket.receive_bytes()
            print(f"📥 Received frame: {len(image_data)} bytes")

            # Process the frame (Phase 1: Recognition)
            result = await attendance_service.process_attendance_frame(image_data)
            
            # Log result safely
            status = result.get('status', 'unknown')
            message = result.get('message', 'No message')
            print(f"📤 Response: status={status}, message={message}")

            # Send result back to frontend
            await websocket.send_json(result)

    except WebSocketDisconnect:
        print("\n🔌 Attendance WebSocket disconnected")
    except Exception as e:
        print(f"\n❌ WebSocket Error: {e}")
        import traceback
        traceback.print_exc()

@router.post("/record")
async def record_attendance(
    user_id: str = Body(..., embed=True),
    attendance_service: AttendanceService = Depends(get_attendance_service)
):
    """
    Phase 5: Record attendance after successful liveness check.
    """
    print(f"\n📝 Recording attendance for user_id: {user_id}")
    return await attendance_service.record_attendance(user_id)

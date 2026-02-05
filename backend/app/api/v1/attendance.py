# backend/app/api/v1/attendance.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Header, status
from pydantic import BaseModel
from typing import Optional, List
from app.domains.attendance.service import AttendanceService
from app.dependencies import get_attendance_service
import time
import json

router = APIRouter()

class AttendanceRecordRequest(BaseModel):
    user_id: str
    liveness: str = "passed"  # "passed" or "failed"
    event_type: str = "check_in"
    session_id: str
    device_id: Optional[str] = "mobile_app"
    attempts_used: Optional[int] = 1
    final_failed_action: Optional[str] = None
    actions_requested: Optional[List[str]] = None
    liveness_start_time: Optional[float] = None  # Unix timestamp when liveness started

class LivenessStartedRequest(BaseModel):
    session_id: str
    user_id: str
    device_id: Optional[str] = "mobile_app"
    actions_requested: Optional[List[str]] = None

class LivenessAttemptRequest(BaseModel):
    session_id: str
    attempt_number: int
    failed_action: Optional[str] = None
    reason: Optional[str] = "timeout"

@router.websocket("/ws/attendance")
async def websocket_endpoint(
    websocket: WebSocket, 
    attendance_service: AttendanceService = Depends(get_attendance_service)
):
    await websocket.accept()
    try:
        while True:
            # Receive data - can be image bytes or JSON with session metadata
            data = await websocket.receive()
            
            # Check if this is a disconnect message
            if data.get("type") == "websocket.disconnect":
                print("🔌 WebSocket client disconnected")
                break
            
            if "bytes" in data:
                # Image data for recognition
                image_data = data["bytes"]
                # Try to get session_id from query params or generate new
                session_id = None
                device_id = "mobile_app"
                
                # Check if WebSocket has query params
                query_params = dict(websocket.query_params) if hasattr(websocket, 'query_params') else {}
                if query_params.get("session_id"):
                    session_id = query_params["session_id"]
                if query_params.get("device_id"):
                    device_id = query_params["device_id"]
                
                result = await attendance_service.process_attendance_frame(
                    image_data, 
                    session_id=session_id,
                    device_id=device_id
                )
                await websocket.send_json(result)
            elif "text" in data:
                # JSON metadata (for future enhancements)
                try:
                    metadata = json.loads(data["text"])
                    # Handle metadata if needed
                except:
                    pass
    except WebSocketDisconnect:
        print("🔌 WebSocket disconnected (exception)")
    except RuntimeError as e:
        # Handle the case where receive() is called after disconnect
        if "disconnect" in str(e).lower():
            print(f"🔌 WebSocket already disconnected: {e}")
        else:
            raise
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("🔌 WebSocket connection closed")

@router.post("/liveness/started")
async def liveness_started(
    request: LivenessStartedRequest, 
    attendance_service: AttendanceService = Depends(get_attendance_service)
):
    """✅ LOG: Liveness session started"""
    await attendance_service.log_liveness_started(
        session_id=request.session_id,
        user_id=request.user_id,
        device_id=request.device_id,
        actions_requested=request.actions_requested
    )
    return {"status": "logged", "message": "Liveness started logged"}

@router.post("/liveness/attempt")
async def liveness_attempt(
    request: LivenessAttemptRequest,
    attendance_service: AttendanceService = Depends(get_attendance_service)
):
    """✅ LOG: Liveness attempt (per retry)"""
    await attendance_service.log_liveness_attempt(
        session_id=request.session_id,
        attempt_number=request.attempt_number,
        failed_action=request.failed_action,
        reason=request.reason
    )
    return {"status": "logged", "message": "Liveness attempt logged"}

@router.post("/record")
async def record_attendance(
    request: AttendanceRecordRequest, 
    attendance_service: AttendanceService = Depends(get_attendance_service)
):
    """✅ LOG: Final attendance record + log liveness result"""
    
    # CRITICAL: Reject immediately if liveness is not "passed"
    if request.liveness != "passed":
        print(f"\n❌ REJECTED: Liveness check failed - NO attendance will be recorded")
        print(f"   User ID: {request.user_id}")
        print(f"   Liveness status: {request.liveness}")
        print(f"   Attempts used: {request.attempts_used}")
        print(f"   Final failed action: {request.final_failed_action}")
        
        # Calculate liveness duration if start time provided (for logging only)
        liveness_duration_ms = None
        if request.liveness_start_time:
            liveness_duration_ms = int((time.time() - request.liveness_start_time) * 1000)
        
        # ✅ LOG 3: Liveness result (FINAL) - logged for failed attempts too
        await attendance_service.log_liveness_result(
            session_id=request.session_id,
            user_id=request.user_id,
            passed=False,
            attempts_used=request.attempts_used or 1,
            final_failed_action=request.final_failed_action,
            duration_ms=liveness_duration_ms
        )
        
        # Return explicit failure response - NO attendance recorded
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "liveness_failed",
                "message": "Liveness check failed. Attendance NOT recorded.",
                "liveness": request.liveness,
                "attempts_used": request.attempts_used or 1,
                "final_failed_action": request.final_failed_action
            }
        )
    
    # Calculate liveness duration if start time provided
    liveness_duration_ms = None
    if request.liveness_start_time:
        # request.liveness_start_time is Unix timestamp (seconds since epoch)
        liveness_duration_ms = int((time.time() - request.liveness_start_time) * 1000)
    
    # ✅ LOG 3: Liveness result (FINAL) - logged first, before attendance record
    await attendance_service.log_liveness_result(
        session_id=request.session_id,
        user_id=request.user_id,
        passed=True,
        attempts_used=request.attempts_used or 1,
        final_failed_action=request.final_failed_action,
        duration_ms=liveness_duration_ms
    )
    
    # CRITICAL: Only record attendance if liveness passed (triple-check)
    # This should never be false due to check above, but extra safety
    if request.liveness == "passed":
        result = await attendance_service.record_attendance(
            user_id=request.user_id, 
            liveness_status=request.liveness,  # Should always be "passed" here
            event_type=request.event_type,
            session_id=request.session_id,
            device_id=request.device_id or "mobile_app",
            attempts_used=request.attempts_used or 1,
            final_failed_action=request.final_failed_action,
            actions_requested=request.actions_requested,
            liveness_start_time=request.liveness_start_time,
            liveness_duration_ms=liveness_duration_ms  # Pass calculated duration
        )
        # Ensure response explicitly indicates success
        if isinstance(result, dict):
            result["status"] = "success"
            result["liveness"] = "passed"
        return result
    else:
        # This should never happen due to check above, but safety check
        print(f"\n❌ CRITICAL ERROR: Reached attendance recording with liveness != 'passed'")
        print(f"   Liveness value: {request.liveness}")
        print(f"   This indicates a logic error in the code!")
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "liveness_failed",
                "message": "Liveness check failed. Attendance not recorded."
            }
        )
# backend/app/domains/attendance/service.py

from typing import Dict, Any, Optional, List
import numpy as np
import cv2
import tempfile
import os
import asyncio
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace

from app.domains.attendance.repository import AttendanceRepository
from app.domains.user.service import UserService
from app.domains.attendance.models import AttendanceLog

class AttendanceService:
    def __init__(self, attendance_repo: AttendanceRepository, user_service: UserService):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self._processing_lock = asyncio.Lock()

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        Phase 1: Real-time Face Recognition.
        Detects face and returns coordinates for a dynamic green frame.
        """
        if self._processing_lock.locked():
            return {"status": "processing", "message": "Processing..."}

        async with self._processing_lock:
            temp_path = None
            try:
                # 1. Decode image to get dimensions
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    return {"status": "error", "message": "Failed to decode image"}
                
                height, width = img.shape[:2]

                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                    temp_path = tmp_file.name
                cv2.imwrite(temp_path, img)

                # 2. Try recognition using the original search_user method
                matched_user = await self.user_service.search_user(image_data)
                
                # 3. Perform detection to get coordinates for the Green Frame
                face_coords = None
                face_detected = False
                
                try:
                    # Use opencv for speed in real-time
                    objs = await run_in_threadpool(
                        DeepFace.extract_faces,
                        img_path=temp_path,
                        detector_backend='opencv',
                        enforce_detection=False,
                        align=False
                    )
                    
                    if len(objs) > 0:
                        face_obj = objs[0]
                        # We accept anything above 0.2 confidence to show the frame
                        if face_obj.get('confidence', 0) > 0.2:
                            area = face_obj['facial_area']
                            face_detected = True
                            face_coords = {
                                "x": float(area['x'] / width),
                                "y": float(area['y'] / height),
                                "w": float(area['w'] / width),
                                "h": float(area['h'] / height)
                            }
                except Exception as e:
                    print(f"DEBUG: Detection error: {e}")

                if matched_user:
                    return {
                        "status": "success",
                        "message": "✔ Face recognized",
                        "user": matched_user.name,
                        "user_id": str(matched_user.id),
                        "face_detected": True,
                        "coords": face_coords
                    }

                if face_detected:
                    return {
                        "status": "fail",
                        "message": "Face detected but not registered",
                        "face_detected": True,
                        "coords": face_coords
                    }

                return {
                    "status": "no_face",
                    "message": "Place your face inside the frame",
                    "face_detected": False
                }

            except Exception as e:
                print(f"DEBUG: Error in process_attendance_frame: {e}")
                return {"status": "error", "message": f"Server Error: {str(e)}"}
            finally:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass

    async def record_attendance(self, user_id: str, liveness_status: str = "pass") -> Dict[str, Any]:
        """Phase 5: Final Recording."""
        log_data = AttendanceLog(user_id=user_id, event_type="check_in", liveness_status=liveness_status)
        await self.attendance_repo.add_log(log_data)
        return {"status": "recorded", "message": "Attendance recorded successfully"}
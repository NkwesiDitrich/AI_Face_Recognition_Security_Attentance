# backend/app/domains/attendance/service.py

"""
Attendance Service Layer
Handles real-time face recognition and attendance logging.
Uses ArcFace for high-accuracy recognition, consistent with the enrollment system.
"""

from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import cv2
import tempfile
import os
import asyncio
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace

from app.domains.attendance.repository import AttendanceRepository
from app.domains.user.service import UserService, RECOGNITION_COSINE_THRESHOLD
from app.domains.attendance.models import AttendanceLog
from app.domains.user.models import User

class AttendanceService:
    def __init__(self, attendance_repo: AttendanceRepository, user_service: UserService):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self._processing_lock = asyncio.Lock()

    def _detect_face_fast(self, img_path: str) -> Dict[str, Any]:
        """
        Fast face detection using OpenCV Haar Cascades.
        Used to provide immediate UI feedback (bounding box) before heavy recognition.
        """
        try:
            img = cv2.imread(img_path)
            if img is None:
                return {"detected": False}
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Load the pre-trained Haar Cascade for face detection
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            
            if len(faces) == 0:
                return {"detected": False}
            
            # Get the largest face in the frame
            (x, y, w, h) = max(faces, key=lambda f: f[2] * f[3])
            
            return {
                "detected": True,
                "coordinates": {
                    "x": int(x),
                    "y": int(y),
                    "width": int(w),
                    "height": int(h),
                }
            }
        except Exception as e:
            print(f"[AttendanceService] Fast detection error: {e}")
            return {"detected": False}

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        PHASE 1: Real-time Face Recognition.
        1. Detects if a face is present.
        2. Extracts ArcFace encoding.
        3. Compares with enrolled users in MongoDB.
        """
        # Prevent overlapping processing of frames
        if self._processing_lock.locked():
            return {"status": "processing", "message": "Processing previous frame..."}

        async with self._processing_lock:
            temp_path = None
            try:
                # Decode image from bytes
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    return {"status": "error", "message": "Failed to decode image"}

                # Save to temporary file for DeepFace processing
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                    temp_path = tmp_file.name
                cv2.imwrite(temp_path, img)

                # 1. Fast detection for UI feedback (Green/Blue frame)
                face_detection = await run_in_threadpool(self._detect_face_fast, temp_path)
                
                if not face_detection["detected"]:
                    return {
                        "status": "no_face",
                        "message": "Place your face inside the frame",
                        "face_detected": False
                    }

                # 2. Recognition using ArcFace (via UserService)
                # This ensures we use the exact same model and logic as enrollment
                matched_user_out = await self.user_service.search_user(image_data)
                
                if matched_user_out:
                    # Success: Face recognized in database
                    return {
                        "status": "success",
                        "message": "✔ Face recognized",
                        "user": matched_user_out.name,
                        "user_id": str(matched_user_out.id),
                        "face_detected": True,
                        "coordinates": face_detection.get("coordinates")
                    }

                # Failure: Face detected but not recognized
                return {
                    "status": "fail",
                    "message": "Face not registered",
                    "face_detected": True,
                    "coordinates": face_detection.get("coordinates")
                }

            except Exception as e:
                print(f"[AttendanceService] Error processing frame: {e}")
                return {"status": "error", "message": f"Server Error: {str(e)}"}
            finally:
                # Clean up temporary file
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except:
                        pass

    async def record_attendance(self, user_id: str, liveness_status: str = "pass") -> Dict[str, Any]:
        """
        PHASE 5: Final Attendance Recording.
        Called after successful face recognition AND liveness check.
        """
        try:
            log_data = AttendanceLog(
                user_id=user_id,
                event_type="check_in",
                liveness_status=liveness_status,
            )
            await self.attendance_repo.add_log(log_data)
            return {
                "status": "recorded", 
                "message": "Attendance recorded successfully",
                "user_id": user_id
            }
        except Exception as e:
            print(f"[AttendanceService] Error recording attendance: {e}")
            return {"status": "error", "message": "Failed to record attendance"}
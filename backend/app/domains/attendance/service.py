from typing import Dict, Any, Optional, Tuple, List
from app.domains.attendance.repository import AttendanceRepository
from app.domains.user.service import UserService, MODEL_NAME, RECOGNITION_COSINE_THRESHOLD
from app.domains.attendance.models import AttendanceLog
from app.domains.user.models import User
from fastapi.concurrency import run_in_threadpool
from deepface import DeepFace
import numpy as np
import cv2
import tempfile
import os
import asyncio

class AttendanceService:
    def __init__(self, attendance_repo: AttendanceRepository, user_service: UserService):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self._processing_lock = asyncio.Lock()

    def _detect_face_with_coordinates(self, img_path: str) -> Dict[str, Any]:
        """
        Detect face and return bounding box coordinates for UI feedback.
        """
        try:
            img = cv2.imread(img_path)
            if img is None:
                return {"detected": False, "coordinates": None}
            
            try:
                # Using retinaface for high accuracy detection
                detections = DeepFace.extract_faces(
                    img_path=img_path,
                    detector_backend='retinaface',
                    enforce_detection=False
                )
                
                if not detections:
                    return {"detected": False, "coordinates": None}
                
                # Get the largest face
                facial_area = max(detections, key=lambda x: x['facial_area']['w'] * x['facial_area']['h'])['facial_area']
                
                return {
                    "detected": True,
                    "coordinates": {
                        "x": int(facial_area['x']),
                        "y": int(facial_area['y']),
                        "width": int(facial_area['w']),
                        "height": int(facial_area['h']),
                    }
                }
            except:
                return {"detected": False, "coordinates": None}
        except:
            return {"detected": False, "coordinates": None}

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        Phase 1: Face Recognition using ArcFace.
        """
        if self._processing_lock.locked():
            return {"status": "processing"}

        async with self._processing_lock:
            temp_path = None
            try:
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                    temp_path = tmp_file.name
                cv2.imwrite(temp_path, img)

                # 1. Detect face for UI feedback
                face_detection = await run_in_threadpool(self._detect_face_with_coordinates, temp_path)
                
                if not face_detection["detected"]:
                    return {
                        "status": "no_face",
                        "message": "Place your face inside the frame",
                        "face_detected": False
                    }

                # 2. Recognition using ArcFace (via UserService)
                encoding = await self.user_service._extract_encoding(image_data, is_enrollment=False)
                
                if not encoding:
                    return {"status": "fail", "message": "Hold still...", "face_detected": True}

                # 3. Search for user in DB
                known_users = await self.user_service.user_repo.get_all_encodings()
                target_vec = self.user_service._l2_normalize(encoding)
                best_match = None

                for user in known_users:
                    if not user.face_encodings: continue
                    known_vec = self.user_service._l2_normalize(user.face_encodings)
                    dist = self.user_service._cosine_distance(target_vec, known_vec)
                    
                    if dist < RECOGNITION_COSINE_THRESHOLD:
                        if best_match is None or dist < best_match[1]:
                            best_match = (user, dist)

                if best_match:
                    return {
                        "status": "success",
                        "message": "✔ Face recognized",
                        "user": best_match[0].name,
                        "user_id": str(best_match[0].id),
                        "face_detected": True
                    }

                return {
                    "status": "fail",
                    "message": "Face not registered",
                    "face_detected": True
                }

            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)

    async def record_attendance(self, user_id: str):
        """
        Phase 5: Final Attendance Recording.
        """
        log_data = AttendanceLog(user_id=user_id, event_type="check_in", liveness_status="pass")
        await self.attendance_repo.add_log(log_data)
        return {"status": "recorded", "message": "Attendance recorded"}
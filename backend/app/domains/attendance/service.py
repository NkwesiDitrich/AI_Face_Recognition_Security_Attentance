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
from app.domains.attendance.models import AttendanceLog

# Cosine threshold for real-time video recognition
RECOGNITION_THRESHOLD = 0.68


class AttendanceService:
    def __init__(self, attendance_repo, user_service):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self._processing_lock = asyncio.Lock()
        self._debug_count = 0

    def _rotate_image(self, image: np.ndarray, angle: int) -> np.ndarray:
        if angle == 90:
            return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            return cv2.rotate(image, cv2.ROTATE_180)
        elif angle == 270:
            return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return image

    async def _detect_and_extract(self, image_data: bytes) -> Dict[str, Any]:
        """
        Robust detection with automatic rotation handling.
        """
        temp_path = None
        try:
            nparr = np.frombuffer(image_data, np.uint8)
            original_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if original_img is None:
                return {"success": False, "message": "Invalid image"}

            # Try 4 rotations: 0, 90, 180, 270
            for angle in [0, 90, 270, 180]:
                img = self._rotate_image(original_img, angle)
                height, width = img.shape[:2]
                
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                    temp_path = tmp_file.name
                cv2.imwrite(temp_path, img)

                try:
                    # Use 'opencv' for speed, but enforce detection
                    results = await run_in_threadpool(
                        DeepFace.represent,
                        img_path=temp_path,
                        model_name="ArcFace",
                        detector_backend="opencv",
                        enforce_detection=True,
                        align=True
                    )

                    if results and len(results) > 0:
                        print(f"[AttendanceService] ✅ Face detected at {angle} degrees!")
                        res = results[0]
                        embedding = res.get("embedding")
                        facial_area = res.get("facial_area", {})
                        
                        coords = {
                            "x": float(facial_area.get("x", 0) / width),
                            "y": float(facial_area.get("y", 0) / height),
                            "w": float(facial_area.get("w", 0) / width),
                            "h": float(facial_area.get("h", 0) / height)
                        }
                        
                        return {
                            "success": True,
                            "embedding": embedding,
                            "coords": coords,
                            "angle": angle
                        }
                except:
                    # If detection fails, try next rotation
                    if temp_path and os.path.exists(temp_path):
                        os.remove(temp_path)
                    continue

            return {"success": False, "message": "No face detected in any orientation"}

        except Exception as e:
            print(f"[AttendanceService] Detection error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        PHASE 1: Real-Time Face Recognition with Auto-Rotation.
        """
        if self._processing_lock.locked():
            return {"status": "processing", "face_detected": False}

        async with self._processing_lock:
            try:
                # 1. Detect and Extract with Auto-Rotation
                result = await self._detect_and_extract(image_data)
                
                if not result.get("success"):
                    return {
                        "status": "no_face",
                        "message": "Place your face inside the frame",
                        "face_detected": False
                    }

                target_encoding = result["embedding"]
                face_coords = result["coords"]

                # 2. Compare with DB
                known_users = await self.user_service.user_repo.get_all_encodings()
                
                if not known_users:
                    return {
                        "status": "fail",
                        "message": "No users enrolled",
                        "face_detected": True,
                        "coords": face_coords
                    }

                target_vec = self.user_service._l2_normalize(target_encoding)
                best_match = None
                min_dist = float('inf')

                for user in known_users:
                    if not user.face_encodings or len(user.face_encodings) != len(target_encoding):
                        continue
                    
                    known_vec = self.user_service._l2_normalize(user.face_encodings)
                    dist = self.user_service._cosine_distance(target_vec, known_vec)
                    
                    if dist < min_dist:
                        min_dist = dist
                        best_match = user

                if best_match and min_dist < RECOGNITION_THRESHOLD:
                    print(f"[AttendanceService] ✅ Recognized: {best_match.name} (dist: {min_dist:.4f})")
                    return {
                        "status": "success",
                        "message": "Face recognized",
                        "user": best_match.name,
                        "user_id": str(best_match.id),
                        "face_detected": True,
                        "coords": face_coords
                    }

                return {
                    "status": "fail",
                    "message": "Face not recognized",
                    "face_detected": True,
                    "coords": face_coords
                }

            except Exception as e:
                print(f"[AttendanceService] Process error: {e}")
                return {"status": "error", "message": str(e)}

    async def record_attendance(self, user_id: str) -> Dict[str, Any]:
        """
        Phase 5: Record attendance
        """
        log = AttendanceLog(user_id=user_id, status="present")
        result = await self.attendance_repo.add_log(log)
        return {"status": "success", "message": "Attendance recorded", "log_id": str(result.id)}
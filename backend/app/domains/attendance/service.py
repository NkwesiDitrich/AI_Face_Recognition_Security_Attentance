# backend/app/domains/attendance/service.py

"""
Attendance Service Layer
Handles real-time face recognition and attendance logging.

PHASE 1: Face Recognition
- Detects if a face is present
- Extracts face encoding
- Compares with enrolled users in MongoDB
- Returns recognition result with user info or "face not registered"
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

    def _detect_face_fast(self, img: np.ndarray) -> Dict[str, Any]:
        """
        Fast face detection using OpenCV Haar Cascades.
        Used to provide immediate UI feedback (bounding box) before heavy recognition.
        """
        try:
            if img is None:
                return {"detected": False}
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Load the pre-trained Haar Cascade for face detection
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            
            # More lenient parameters for detection in various positions
            faces = face_cascade.detectMultiScale(
                gray, 
                scaleFactor=1.05, # Smaller scale factor for better detection
                minNeighbors=3,   # Lower neighbors for more sensitivity
                minSize=(30, 30)
            )
            
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

    async def _extract_encoding_with_fallback(self, img: np.ndarray) -> Optional[List[float]]:
        """
        Extract face encoding with robust detection logic for real-time recognition.
        """
        temp_path = None
        try:
            # Save to temporary file for DeepFace
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                temp_path = tmp_file.name
            cv2.imwrite(temp_path, img)
            
            # Try multiple detector backends in order of preference for real-time
            # Added 'retinaface' as a final strict fallback before relaxed mode
            detector_backends = ["opencv", "mediapipe", "mtcnn", "retinaface"]
            
            for backend in detector_backends:
                try:
                    print(f"[AttendanceService] Trying detection with {backend}...")
                    represent_output = await run_in_threadpool(
                        DeepFace.represent,
                        img_path=temp_path,
                        model_name="ArcFace",
                        detector_backend=backend,
                        align=True,
                        enforce_detection=True,
                    )
                    
                    embedding = self.user_service._parse_deepface_embedding(represent_output)
                    if embedding:
                        print(f"[AttendanceService] ✅ Encoding extracted with {backend}")
                        return embedding
                            
                except Exception as e:
                    print(f"[AttendanceService] ⚠️ {backend} detection failed: {e}")
                    continue

            # Last resort: try with relaxed detection (enforce_detection=False)
            print("[AttendanceService] 🔄 Trying relaxed detection...")
            try:
                represent_output = await run_in_threadpool(
                    DeepFace.represent,
                    img_path=temp_path,
                    model_name="ArcFace",
                    detector_backend="opencv",
                    align=True,
                    enforce_detection=False,
                )
                
                embedding = self.user_service._parse_deepface_embedding(represent_output)
                if embedding:
                    print(f"[AttendanceService] ✅ Encoding extracted with relaxed detection")
                    return embedding
                        
            except Exception as e:
                print(f"[AttendanceService] ⚠️ Relaxed detection failed: {e}")

            print("[AttendanceService] ❌ All detection methods failed")
            return None

        except Exception as e:
            print(f"[AttendanceService] Error in encoding extraction: {e}")
            return None
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        PHASE 1: Real-time Face Recognition.
        """
        # Prevent overlapping processing of frames
        if self._processing_lock.locked():
            return {
                "status": "processing", 
                "message": "Processing previous frame...",
                "face_detected": False
            }

        async with self._processing_lock:
            try:
                # Decode image once
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if img is None:
                    return {
                        "status": "error", 
                        "message": "Failed to decode image",
                        "face_detected": False
                    }

                # Step 1: Fast detection for UI feedback
                face_detection = self._detect_face_fast(img)
                
                # Step 2: If no face detected, return immediately
                if not face_detection.get("detected"):
                    return {
                        "status": "no_face",
                        "message": "Place your face inside the frame",
                        "face_detected": False
                    }
                
                print(f"[AttendanceService] Face detected at {face_detection.get('coordinates')}")
                
                # Step 3: Extract encoding with fallback strategies
                print("[AttendanceService] 🔍 Extracting face encoding for recognition...")
                target_encoding = await self._extract_encoding_with_fallback(img)
                
                if not target_encoding:
                    print("[AttendanceService] ❌ Failed to extract encoding")
                    return {
                        "status": "fail",
                        "message": "Could not process face. Please try again.",
                        "face_detected": True,
                        "coordinates": face_detection.get("coordinates")
                    }
                
                # Step 4: Compare with enrolled users
                print("[AttendanceService] 🔄 Comparing with enrolled users...")
                known_users = await self.user_service.user_repo.get_all_encodings()
                
                if not known_users:
                    print("[AttendanceService] ⚠️ No users enrolled yet")
                    return {
                        "status": "fail",
                        "message": "No users registered in system",
                        "face_detected": True,
                        "coordinates": face_detection.get("coordinates")
                    }
                
                target_vec = self.user_service._l2_normalize(target_encoding)
                best_match = None
                best_distance = float('inf')
                
                # Use threshold from UserService
                RECOGNITION_THRESHOLD = RECOGNITION_COSINE_THRESHOLD
                
                for user in known_users:
                    if not user.face_encodings:
                        continue
                    
                    if len(user.face_encodings) != len(target_encoding):
                        continue
                    
                    known_vec = self.user_service._l2_normalize(user.face_encodings)
                    dist = self.user_service._cosine_distance(target_vec, known_vec)
                    
                    if dist < best_distance:
                        best_distance = dist
                        best_match = user
                
                # Step 5: Return result
                if best_match and best_distance < RECOGNITION_THRESHOLD:
                    print(f"[AttendanceService] ✅ MATCH FOUND: {best_match.name} (distance: {best_distance:.4f})")
                    return {
                        "status": "success",
                        "message": "✔ Face recognized",
                        "name": best_match.name,
                        "user_id": str(best_match.id),
                        "face_detected": True,
                        "coordinates": face_detection.get("coordinates"),
                        "confidence": float(1.0 - best_distance)
                    }
                else:
                    print(f"[AttendanceService] ❌ NO MATCH: Best distance {best_distance:.4f} >= threshold {RECOGNITION_THRESHOLD}")
                    return {
                        "status": "not_recognized",
                        "message": "Face detected but not registered",
                        "face_detected": True,
                        "coordinates": face_detection.get("coordinates")
                    }

            except Exception as e:
                print(f"[AttendanceService] Error processing frame: {e}")
                return {
                    "status": "error", 
                    "message": f"Server Error: {str(e)}",
                    "face_detected": False
                }

    async def record_attendance(self, user_id: str, liveness_status: str = "pass") -> Dict[str, Any]:
        """
        PHASE 5: Final Attendance Recording.
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
            return {
                "status": "error",
                "message": f"Failed to record attendance: {str(e)}",
                "user_id": user_id
            }
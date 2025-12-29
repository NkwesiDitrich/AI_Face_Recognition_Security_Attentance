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

    async def _extract_encoding_with_fallback(self, image_data: bytes) -> Optional[List[float]]:
        """
        Extract face encoding with robust detection logic for real-time recognition.
        
        This method tries multiple approaches to extract a good quality encoding:
        1. Try with OpenCV detector (fastest)
        2. Try with MTCNN (better for various angles)
        3. Try with RetinaFace (most accurate but slow)
        4. Last resort: relaxed detection with OpenCV
        """
        temp_path = None
        try:
            # Decode image from bytes
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                print("[AttendanceService] Failed to decode image")
                return None

            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                temp_path = tmp_file.name
            cv2.imwrite(temp_path, img)
            
            print(f"[AttendanceService] Processing image: {temp_path}")

            # Try multiple detector backends in order of preference for real-time
            detector_backends = ["opencv", "mtcnn", "retinaface"]
            
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
                    
                    if represent_output and len(represent_output) > 0:
                        first = represent_output[0]
                        if isinstance(first, dict) and "embedding" in first:
                            embedding = first["embedding"]
                            if isinstance(embedding, list) and len(embedding) >= 100:
                                print(f"[AttendanceService] ✅ Encoding extracted with {backend}")
                                return embedding
                        elif isinstance(first, list) and len(first) >= 100:
                            print(f"[AttendanceService] ✅ Encoding extracted with {backend} (direct list)")
                            return first
                            
                except Exception as e:
                    print(f"[AttendanceService] ⚠️ {backend} detection failed: {e}")
                    continue

            # Last resort: try with relaxed detection
            print("[AttendanceService] 🔄 Trying relaxed detection...")
            try:
                represent_output = await run_in_threadpool(
                    DeepFace.represent,
                    img_path=temp_path,
                    model_name="ArcFace",
                    detector_backend="opencv",
                    align=True,
                    enforce_detection=False,  # Relaxed detection
                )
                
                if represent_output and len(represent_output) > 0:
                    first = represent_output[0]
                    if isinstance(first, dict) and "embedding" in first:
                        embedding = first["embedding"]
                        if isinstance(embedding, list) and len(embedding) >= 100:
                            print(f"[AttendanceService] ✅ Encoding extracted with relaxed detection")
                            return embedding
                    elif isinstance(first, list) and len(first) >= 100:
                        print(f"[AttendanceService] ✅ Encoding extracted with relaxed detection (direct list)")
                        return first
                        
            except Exception as e:
                print(f"[AttendanceService] ⚠️ Relaxed detection failed: {e}")

            print("[AttendanceService] ❌ All detection methods failed")
            return None

        except Exception as e:
            print(f"[AttendanceService] Error in encoding extraction: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            # Clean up temporary file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        PHASE 1: Real-time Face Recognition.
        
        Flow:
        1. Prevent overlapping frame processing
        2. Fast face detection for UI feedback (green/blue frame)
        3. Extract face encoding with multiple fallback strategies
        4. Compare with enrolled users in database
        5. Return success/fail response
        
        Returns:
        - success: Face recognized (return user info)
        - no_face: No face detected (ask user to place face in frame)
        - fail: Face detected but not recognized (not in database)
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
                # Step 1: Fast detection for UI feedback
                temp_path = None
                try:
                    nparr = np.frombuffer(image_data, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    if img is None:
                        return {
                            "status": "error", 
                            "message": "Failed to decode image",
                            "face_detected": False
                        }

                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                        temp_path = tmp_file.name
                    cv2.imwrite(temp_path, img)
                    
                    # Fast detection for UI feedback
                    face_detection = await run_in_threadpool(
                        self._detect_face_fast, temp_path
                    )
                    
                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                
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
                target_encoding = await self._extract_encoding_with_fallback(image_data)
                
                if not target_encoding:
                    print("[AttendanceService] ❌ Failed to extract encoding")
                    return {
                        "status": "fail",
                        "message": "Could not process face. Please try again.",
                        "face_detected": True,
                        "coordinates": face_detection.get("coordinates")
                    }
                
                print(f"[AttendanceService] ✅ Encoding extracted successfully! Length: {len(target_encoding)}")
                
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
                
                print(f"[AttendanceService] Comparing against {len(known_users)} enrolled users")
                
                # Use the same matching logic as UserService but with more lenient threshold
                target_vec = self.user_service._l2_normalize(target_encoding)
                best_match = None
                best_distance = float('inf')
                
                # More lenient threshold for real-time recognition (0.45 instead of 0.40)
                RECOGNITION_THRESHOLD = 0.45
                
                for user in known_users:
                    if not user.face_encodings:
                        continue
                    
                    # Skip if encoding sizes differ
                    if len(user.face_encodings) != len(target_encoding):
                        print(f"[AttendanceService] ⚠️ Skipping {user.name}: encoding size mismatch")
                        continue
                    
                    known_vec = self.user_service._l2_normalize(user.face_encodings)
                    dist = self.user_service._cosine_distance(target_vec, known_vec)
                    
                    print(f"[AttendanceService] Distance to {user.name}: {dist:.4f}")
                    
                    if dist < best_distance:
                        best_distance = dist
                        best_match = user
                
                # Step 5: Return result
                if best_match and best_distance < RECOGNITION_THRESHOLD:
                    print(f"[AttendanceService] ✅ MATCH FOUND: {best_match.name} (distance: {best_distance:.4f})")
                    return {
                        "status": "success",
                        "message": "✔ Face recognized",
                        "user": best_match.name,
                        "user_id": str(best_match.id),
                        "face_detected": True,
                        "coordinates": face_detection.get("coordinates"),
                        "confidence": float(1.0 - best_distance)  # Confidence score
                    }
                else:
                    print(f"[AttendanceService] ❌ NO MATCH: Best distance {best_distance:.4f} >= threshold {RECOGNITION_THRESHOLD}")
                    return {
                        "status": "fail",
                        "message": "Face not registered",
                        "face_detected": True,
                        "coordinates": face_detection.get("coordinates"),
                        "debug": {
                            "best_distance": best_distance,
                            "threshold": RECOGNITION_THRESHOLD
                        }
                    }

            except Exception as e:
                print(f"[AttendanceService] Error processing frame: {e}")
                import traceback
                traceback.print_exc()
                return {
                    "status": "error", 
                    "message": f"Server Error: {str(e)}",
                    "face_detected": False
                }

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
            return {
                "status": "error",
                "message": f"Failed to record attendance: {str(e)}",
                "user_id": user_id
            }

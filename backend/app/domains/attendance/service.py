# backend/app/domains/attendance/service.py
# ✅ PHASE 1 COMPLETE: Face Detection + Recognition (combined)

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

# Threshold for recognition
RECOGNITION_THRESHOLD = 0.50

# Detection settings
MODEL_NAME = "ArcFace"
DETECTOR_BACKENDS = ["retinaface", "mtcnn", "opencv", "mediapipe"]
ALIGN = True


class AttendanceService:
    def __init__(self, attendance_repo, user_service):
        self.attendance_repo = attendance_repo
        self.user_service = user_service
        self._processing_lock = asyncio.Lock()

    def _parse_deepface_embedding(self, represent_output: Any) -> Optional[List[float]]:
        """Parse DeepFace.represent() output."""
        if represent_output is None:
            return None

        if isinstance(represent_output, np.ndarray):
            emb = represent_output.flatten().tolist()
            return emb if len(emb) >= 512 else None

        if isinstance(represent_output, list) and len(represent_output) > 0:
            first = represent_output[0]

            if isinstance(first, dict) and "embedding" in first:
                emb = first["embedding"]
                if isinstance(emb, np.ndarray):
                    emb = emb.flatten().tolist()
                if isinstance(emb, list) and len(emb) >= 512:
                    return [float(v) for v in emb]
                return None

            if isinstance(first, (int, float)):
                if len(represent_output) >= 512:
                    return [float(v) for v in represent_output]
                return None

        return None

    async def process_attendance_frame(self, image_data: bytes) -> Dict[str, Any]:
        """
        PHASE 1 - Complete Face Recognition Flow:
        1. Detect face
        2. Extract embedding
        3. Compare with enrolled users
        4. Return result
        """
        if self._processing_lock.locked():
            return {
                "status": "processing",
                "message": "Processing...",
                "face_detected": False
            }

        async with self._processing_lock:
            try:
                print("\n" + "="*60)
                print("🎯 PHASE 1 - Face Detection + Recognition")
                print("="*60)

                # Decode image
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if img is None:
                    return {
                        "status": "error",
                        "message": "Invalid image",
                        "face_detected": False
                    }

                print(f"✅ Image decoded: {img.shape}")

                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                        temp_path = tmp_file.name
                    cv2.imwrite(temp_path, img)
                    print(f"✅ Saved: {temp_path}")

                    # Detect face and extract embedding
                    print("🔍 Detecting face...")

                    embedding = None
                    facial_area = {}

                    # Try strict detection first
                    for backend in DETECTOR_BACKENDS:
                        try:
                            represent_output = await run_in_threadpool(
                                DeepFace.represent,
                                img_path=temp_path,
                                model_name=MODEL_NAME,
                                detector_backend=backend,
                                align=ALIGN,
                                enforce_detection=True,
                            )

                            raw_embedding = self._parse_deepface_embedding(represent_output)
                            
                            if raw_embedding:
                                print(f"✅ Face detected with backend: {backend}")
                                embedding = raw_embedding
                                
                                if isinstance(represent_output, list) and len(represent_output) > 0:
                                    first = represent_output[0]
                                    if isinstance(first, dict):
                                        facial_area = first.get("facial_area", {})
                                
                                break
                                
                        except Exception as e:
                            print(f"⚠️ Backend {backend} failed")
                            continue

                    # If strict failed, try lenient
                    if embedding is None:
                        print("🔄 Trying lenient detection...")
                        try:
                            represent_output = await run_in_threadpool(
                                DeepFace.represent,
                                img_path=temp_path,
                                model_name=MODEL_NAME,
                                detector_backend="opencv",
                                align=ALIGN,
                                enforce_detection=False,
                            )

                            raw_embedding = self._parse_deepface_embedding(represent_output)
                            
                            if raw_embedding:
                                print("✅ Face detected with lenient detection")
                                embedding = raw_embedding
                                # Lenient detection doesn't return facial_area, estimate it
                                img_height, img_width = img.shape[:2]
                                face_size = min(img_width, img_height) // 3
                                center_x = img_width // 2
                                center_y = img_height // 2
                                facial_area = {
                                    "x": center_x - face_size // 2,
                                    "y": center_y - face_size // 2,
                                    "w": face_size,
                                    "h": face_size
                                }
                        
                        except Exception as e:
                            print(f"❌ Detection failed: {str(e)[:50]}")

                    # No face detected
                    if embedding is None:
                        print("❌ No face detected")
                        return {
                            "status": "no_face",
                            "message": "Place your face inside the frame",
                            "face_detected": False
                        }

                    print(f"✅ Face detected! Embedding length: {len(embedding)}")

                    # Calculate face size
                    img_height, img_width = img.shape[:2]
                    face_w = facial_area.get("w", 0)
                    face_size_percent = (face_w / img_width) * 100 if face_w > 0 else 25

                    print(f"✅ Face size: {face_size_percent:.1f}% of screen width")

                    # Get enrolled users
                    print("🔍 Fetching enrolled users...")
                    known_users = await self.user_service.user_repo.get_all_encodings()

                    if not known_users:
                        print("⚠️ No users enrolled")
                        return {
                            "status": "fail",
                            "message": "No users registered in system",
                            "face_detected": True,
                            "face_size_percent": face_size_percent
                        }

                    print(f"✅ Found {len(known_users)} enrolled users")

                    # Compare with enrolled users
                    print("🔄 Comparing with enrolled users...")

                    target_vec = self.user_service._l2_normalize(embedding)
                    best_match = None
                    best_distance = float('inf')
                    best_user_name = "Unknown"

                    for user in known_users:
                        if not user.face_encodings:
                            continue

                        if len(user.face_encodings) != len(embedding):
                            continue

                        known_vec = self.user_service._l2_normalize(user.face_encodings)
                        distance = self.user_service._cosine_distance(target_vec, known_vec)

                        print(f"   Distance to {user.name}: {distance:.4f} (threshold: {RECOGNITION_THRESHOLD})")

                        if distance < best_distance:
                            best_distance = distance
                            best_match = user
                            best_user_name = user.name

                    print(f"\n🏆 Best match: {best_user_name}")
                    print(f"   Best distance: {best_distance:.4f}")
                    print(f"   Threshold: {RECOGNITION_THRESHOLD}")

                    # Return result
                    if best_match and best_distance < RECOGNITION_THRESHOLD:
                        print(f"✅ SUCCESS: {best_user_name} is recognized!")

                        return {
                            "status": "success",
                            "message": "Face recognized",
                            "user": best_user_name,
                            "user_id": str(best_match.id),
                            "face_detected": True,
                            "face_size_percent": face_size_percent,
                            "distance": best_distance,
                            "confidence": float(1.0 - best_distance)
                        }
                    else:
                        if best_match:
                            print(f"❌ FAIL: Distance {best_distance:.4f} >= threshold {RECOGNITION_THRESHOLD}")
                        else:
                            print("❌ FAIL: No match found")

                        return {
                            "status": "fail",
                            "message": "Face not registered",
                            "face_detected": True,
                            "face_size_percent": face_size_percent,
                            "distance": best_distance
                        }

                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                            print("🧹 Cleaned up temp file")
                        except:
                            pass

            except Exception as e:
                print(f"❌ Error: {e}")
                import traceback
                traceback.print_exc()
                return {
                    "status": "error",
                    "message": str(e),
                    "face_detected": False
                }

    async def record_attendance(self, user_id: str) -> Dict[str, Any]:
        """Record attendance after successful recognition."""
        try:
            log = AttendanceLog(user_id=user_id, status="present")
            result = await self.attendance_repo.add_log(log)
            return {
                "status": "success",
                "message": "Attendance recorded",
                "log_id": str(result.id)
            }
        except Exception as e:
            print(f"❌ Recording error: {e}")
            return {"status": "error", "message": str(e)}

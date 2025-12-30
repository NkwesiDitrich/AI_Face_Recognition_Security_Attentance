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

# Threshold for recognition
# Synchronized with UserService.RECOGNITION_COSINE_THRESHOLD = 0.40
# We'll use 0.40 to be strict, or 0.45 if we want to be slightly more lenient.
# Let's stick to 0.45 for better user experience as requested.
RECOGNITION_THRESHOLD = 0.45 

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
        1. Receive frame & Decode image
        2. Detect face (If NO face: return { status: "no_face" })
        3. Signal "face_detected" to frontend
        4. Extract embedding (ArcFace)
        5. Compare embedding with DB embeddings (Cosine distance)
        6. Check threshold (If distance > threshold: return { status: "not_recognized" })
        7. Return { status: "recognized", user_id, name }
        """
        if self._processing_lock.locked():
            return {
                "status": "processing",
                "message": "Processing...",
                "face_detected": False
            }

        async with self._processing_lock:
            try:
                # Decode image
                nparr = np.frombuffer(image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if img is None:
                    return {
                        "status": "error",
                        "message": "Invalid image",
                        "face_detected": False
                    }

                temp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                        temp_path = tmp_file.name
                    cv2.imwrite(temp_path, img)

                    embedding = None

                    # 1. Try strict detection with multiple backends
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
                                embedding = raw_embedding
                                print(f"DEBUG: Face detected with backend: {backend}")
                                break
                        except:
                            continue

                    # 2. If strict failed, try lenient detection (enforce_detection=False)
                    if embedding is None:
                        try:
                            represent_output = await run_in_threadpool(
                                DeepFace.represent,
                                img_path=temp_path,
                                model_name=MODEL_NAME,
                                detector_backend="opencv", # Fast fallback
                                align=ALIGN,
                                enforce_detection=False,
                            )
                            embedding = self._parse_deepface_embedding(represent_output)
                            if embedding:
                                print("DEBUG: Face detected with lenient detection (OpenCV)")
                        except:
                            pass

                    # No face detected even with lenient approach
                    if embedding is None:
                        return {
                            "status": "no_face",
                            "message": "Face not detected",
                            "face_detected": False
                        }

                    # FACE DETECTED! Log it explicitly as requested
                    print("DEBUG: Face detected! Proceeding to recognition...")
                    
                    # Get enrolled users
                    known_users = await self.user_service.user_repo.get_all_encodings()

                    if not known_users:
                        print("DEBUG: No users enrolled in the database.")
                        return {
                            "status": "not_recognized",
                            "message": "Face not registered",
                            "face_detected": True
                        }

                    # Compare with enrolled users
                    # IMPORTANT: We use the exact same normalization and distance as UserService
                    target_vec = self.user_service._l2_normalize(embedding)
                    best_match = None
                    best_distance = float('inf')

                    for user in known_users:
                        if not user.face_encodings or len(user.face_encodings) != len(embedding):
                            continue

                        known_vec = self.user_service._l2_normalize(user.face_encodings)
                        distance = self.user_service._cosine_distance(target_vec, known_vec)

                        if distance < best_distance:
                            best_distance = distance
                            best_match = user

                    # Return result based on threshold
                    if best_match and best_distance <= RECOGNITION_THRESHOLD:
                        print(f"DEBUG: Face recognized as {best_match.name} (Distance: {best_distance:.4f})")
                        return {
                            "status": "recognized",
                            "user_id": str(best_match.id),
                            "name": best_match.name,
                            "face_detected": True,
                            "distance": round(float(best_distance), 4)
                        }
                    else:
                        if best_match:
                            print(f"DEBUG: Face NOT recognized. Best match: {best_match.name} (Distance: {best_distance:.4f}, Threshold: {RECOGNITION_THRESHOLD})")
                        else:
                            print("DEBUG: Face NOT recognized. No match found in database.")
                            
                        return {
                            "status": "not_recognized",
                            "message": "Face not registered",
                            "face_detected": True,
                            "distance": round(float(best_distance), 4) if best_match else None
                        }

                finally:
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except:
                            pass

            except Exception as e:
                print(f"DEBUG: Error in process_attendance_frame: {e}")
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
            return {"status": "error", "message": str(e)}
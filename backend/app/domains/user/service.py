# backend/app/domains/user/service.py

"""
User Service Layer
Business logic for user enrollment and face recognition

Improvements:
- Uses ArcFace (State-of-the-art accuracy)
- Improved face detection logic with fallback to enforce_detection=False for problematic images
- Proper Cosine thresholds for ArcFace
- L2-normalized cosine distance for duplicate detection + search
"""

from typing import Optional, List, Union, Dict, Any
import numpy as np
import cv2
import os
import tempfile

from deepface import DeepFace
from fastapi.concurrency import run_in_threadpool

from app.domains.user.models import User
from app.domains.user.schemas import UserCreate, UserOut
from app.domains.user.repository import UserRepository
from app.domains.system_log.repository import SystemLogRepository
from app.domains.system_log.models import SystemLog
from datetime import datetime
import time


# ---------------------------
# Model settings
# ---------------------------
MODEL_NAME = "ArcFace"
MIN_EMBEDDING_LENGTH = 512  # ArcFace uses 512-dimensional vectors

# Try multiple detectors (since camera/emulator quality varies)
# Added 'mediapipe' as it's often more robust for mobile captures
DETECTOR_BACKENDS = ["retinaface", "mtcnn", "opencv", "mediapipe"]
ALIGN = True

# ---------------------------
# Cosine thresholds for ArcFace
# ---------------------------
# Lower cosine distance = more similar
# 0.40 is the recommended threshold for ArcFace with Cosine distance
DUPLICATE_COSINE_THRESHOLD = 0.40
RECOGNITION_COSINE_THRESHOLD = 0.40


class UserService:
    def __init__(self, user_repo: UserRepository, system_log_repo: SystemLogRepository = None):
        self.user_repo = user_repo
        self.system_log_repo = system_log_repo  # Optional - will be None if not injected

    # -----------------------------
    # Helpers
    # -----------------------------
    def _is_number(self, x: Any) -> bool:
        return isinstance(x, (int, float, np.number))

    def _l2_normalize(self, vec: List[float]) -> np.ndarray:
        arr = np.array(vec, dtype=np.float32)
        norm = np.linalg.norm(arr)
        return arr if norm == 0 else (arr / norm)

    def _cosine_distance(self, a: np.ndarray, b: np.ndarray) -> float:
        # DeepFace's internal cosine distance is 1 - cosine_similarity
        # cosine_similarity = (a . b) / (||a|| * ||b||)
        # Since we L2 normalize, ||a|| = ||b|| = 1, so similarity = a . b
        return float(1.0 - np.dot(a, b))

    def _parse_deepface_embedding(self, represent_output: Any) -> Optional[List[float]]:
        """
        Parse DeepFace.represent() output across different versions.
        """
        if represent_output is None:
            return None

        if isinstance(represent_output, np.ndarray):
            emb = represent_output.flatten().tolist()
            return emb if len(emb) >= MIN_EMBEDDING_LENGTH else None

        if isinstance(represent_output, list) and len(represent_output) > 0:
            first = represent_output[0]

            if isinstance(first, dict) and "embedding" in first:
                emb = first["embedding"]
                if isinstance(emb, np.ndarray):
                    emb = emb.flatten().tolist()
                if isinstance(emb, list) and len(emb) >= MIN_EMBEDDING_LENGTH and all(self._is_number(v) for v in emb):
                    return [float(v) for v in emb]
                return None

            if self._is_number(first):
                if len(represent_output) >= MIN_EMBEDDING_LENGTH and all(self._is_number(v) for v in represent_output):
                    return [float(v) for v in represent_output]
                return None

        return None

    # -----------------------------
    # Improved encoding extraction
    # -----------------------------
    async def _extract_encoding(self, image_data: bytes, is_enrollment: bool = False) -> Optional[List[float]]:
        """
        Extract face encoding with robust detection logic.
        """
        temp_path = None
        try:
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                print("❌ OpenCV failed to decode image.")
                return None

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                temp_path = tmp_file.name

            if not cv2.imwrite(temp_path, img):
                print(f"❌ Failed to write image to {temp_path}")
                return None

            print(f"✅ Image saved to: {temp_path}")

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

                    embedding = self._parse_deepface_embedding(represent_output)
                    if embedding:
                        print(f"✅ Embedding extracted successfully! (backend={backend})")
                        return embedding
                except Exception as e:
                    print(f"⚠️ Strict detection failed (backend={backend}): {e}")
                    continue

            # If enrollment and strict failed, we might want to reject
            # But for search/attendance, we can try a more relaxed approach
            if not is_enrollment:
                print("🔄 Strict detection failed, trying relaxed detection for search...")
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
                        print("✅ Embedding extracted with relaxed detection.")
                        return embedding
                except Exception as e:
                    print(f"❌ Relaxed detection also failed: {e}")

            return None

        except Exception as e:
            print(f"❌ Error during face encoding: {e}")
            return None

        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

    # -----------------------------
    # Duplicate detection
    # -----------------------------
    async def _check_duplicate_enrollment(self, new_encoding: List[float]) -> Optional[User]:
        existing_users = await self.user_repo.get_all_encodings()

        if not existing_users:
            return None

        new_vec = self._l2_normalize(new_encoding)
        best_match = None

        for user in existing_users:
            if not user.face_encodings or len(user.face_encodings) != len(new_encoding):
                continue

            known_vec = self._l2_normalize(user.face_encodings)
            dist = self._cosine_distance(new_vec, known_vec)

            if best_match is None or dist < best_match[1]:
                best_match = (user, dist)

        if best_match:
            user, dist = best_match
            print(f"🧪 Best duplicate candidate: '{user.name}' distance={dist:.4f}")
            if dist < DUPLICATE_COSINE_THRESHOLD:
                return user

        return None

    # -----------------------------
    # Enrollment
    # -----------------------------
    async def enroll_user(
        self,
        user_data: UserCreate,
        image_data: bytes,
        device_id: str = "mobile_app",
        initiated_by: str = "mobile_app"
    ) -> Union[UserOut, Dict[str, Any], None]:
        
        start_time = time.time()
        
        # ✅ LOG 1: Enrollment started
        if self.system_log_repo:
            try:
                await self.system_log_repo.add_log(SystemLog(
                    type="face_enrollment",
                    stage="started",
                    user_id=None,  # Not yet created
                    initiated_by=initiated_by,
                    device_id=device_id,
                    metadata={"name": user_data.name, "employee_id": user_data.employee_id}
                ))
            except Exception as e:
                print(f"⚠️ Failed to log enrollment started: {e}")

        print(f"📸 Extracting face encoding for user: {user_data.name}")
        encoding = await self._extract_encoding(image_data, is_enrollment=True)

        if not encoding:
            print(f"❌ Face detection/encoding failed for {user_data.name}")
            # ✅ LOG: Enrollment failed
            if self.system_log_repo:
                try:
                    duration_ms = int((time.time() - start_time) * 1000)
                    await self.system_log_repo.add_log(SystemLog(
                        type="face_enrollment",
                        stage="failed",
                        reason="face_detection_failed",
                        duration_ms=duration_ms,
                        device_id=device_id,
                        initiated_by=initiated_by,
                        metadata={"name": user_data.name, "employee_id": user_data.employee_id}
                    ))
                except Exception as e:
                    print(f"⚠️ Failed to log enrollment failed: {e}")
            return None

        print("🔍 Checking for duplicate enrollment...")
        duplicate_user = await self._check_duplicate_enrollment(encoding)
        if duplicate_user:
            print(f"❌ Enrollment rejected: Duplicate face detected (matches {duplicate_user.name})")
            # ✅ LOG: Enrollment failed (duplicate)
            if self.system_log_repo:
                try:
                    duration_ms = int((time.time() - start_time) * 1000)
                    await self.system_log_repo.add_log(SystemLog(
                        type="face_enrollment",
                        stage="failed",
                        reason="duplicate_face",
                        duration_ms=duration_ms,
                        device_id=device_id,
                        initiated_by=initiated_by,
                        metadata={
                            "name": user_data.name,
                            "employee_id": user_data.employee_id,
                            "existing_user_id": str(duplicate_user.id),
                            "existing_user_name": duplicate_user.name
                        }
                    ))
                except Exception as e:
                    print(f"⚠️ Failed to log enrollment duplicate: {e}")
            return {
                "error": "duplicate",
                "message": f"Face already registered as {duplicate_user.name}",
                "existing_user_id": str(duplicate_user.id),
                "existing_user_name": duplicate_user.name,
                "existing_employee_id": duplicate_user.employee_id,
            }

        # ✅ REMOVED: image_base64 - images should not be stored in database
        new_user = User(
            name=user_data.name,
            employee_id=user_data.employee_id,
            access_level=user_data.access_level,
            face_encodings=encoding,
        )

        saved_user = await self.user_repo.add_user(new_user)
        duration_ms = int((time.time() - start_time) * 1000)
        
        # ✅ LOG 2: Enrollment completed (SUCCESS)
        if self.system_log_repo:
            try:
                await self.system_log_repo.add_log(SystemLog(
                    type="face_enrollment",
                    stage="completed",
                    user_id=str(saved_user.id),
                    embedding_size=len(encoding),
                    model_version=MODEL_NAME,
                    duration_ms=duration_ms,
                    device_id=device_id,
                    initiated_by=initiated_by
                ))
            except Exception as e:
                print(f"⚠️ Failed to log enrollment completed: {e}")
        
        return UserOut(
            id=str(saved_user.id),
            name=saved_user.name,
            employee_id=saved_user.employee_id,
            access_level=saved_user.access_level,
        )

    # -----------------------------
    # Search / recognition
    # -----------------------------
    async def search_user(self, image_data: bytes) -> Optional[UserOut]:
        target_encoding = await self._extract_encoding(image_data, is_enrollment=False)
        if not target_encoding:
            return None

        known_users = await self.user_repo.get_all_encodings()
        if not known_users:
            return None

        target_vec = self._l2_normalize(target_encoding)
        best_match = None

        for user in known_users:
            if not user.face_encodings or len(user.face_encodings) != len(target_encoding):
                continue

            known_vec = self._l2_normalize(user.face_encodings)
            dist = self._cosine_distance(target_vec, known_vec)

            if dist < RECOGNITION_COSINE_THRESHOLD:
                if best_match is None or dist < best_match[1]:
                    best_match = (user, dist)

        if best_match:
            matched_user, dist = best_match
            print(f"✅ Recognition match: {matched_user.name} (distance={dist:.4f})")
            return UserOut(
                id=str(matched_user.id),
                name=matched_user.name,
                employee_id=matched_user.employee_id,
                access_level=matched_user.access_level,
            )

        return None
# backend/app/domains/user/service.py

"""
User Service Layer
Business logic for user enrollment and face recognition

FINAL HYBRID VERSION:
- Uses ArcFace (best accuracy)
- Uses simple DeepFace.represent() flow (compatible with your installed version)
- Robust output parsing (handles list/dict/numpy returns)
- L2-normalized cosine distance for matching
- Strict duplicate threshold
"""

from typing import Optional, List, Union, Dict, Any
import numpy as np
import cv2
import os
import tempfile
import base64

from deepface import DeepFace
from fastapi.concurrency import run_in_threadpool

from app.domains.user.models import User
from app.domains.user.schemas import UserCreate, UserOut
from app.domains.user.repository import UserRepository


# ---------------------------
# Model settings
# ---------------------------
MODEL_NAME = "ArcFace"
MIN_EMBEDDING_LENGTH = 200  # ArcFace is 512 dims

# ---------------------------
# Thresholds (cosine distance)
# ---------------------------
# Lower = more similar
DUPLICATE_COSINE_THRESHOLD = 0.25      # Strict for duplicates
RECOGNITION_COSINE_THRESHOLD = 0.35    # Slightly looser for recognition


class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

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
        return float(1.0 - np.dot(a, b))

    def _parse_deepface_embedding(self, represent_output: Any) -> Optional[List[float]]:
        """
        Robust parsing for DeepFace.represent() output.
        Handles: List[Dict], List[float], np.ndarray
        """
        if represent_output is None:
            return None

        # Case 1: numpy array
        if isinstance(represent_output, np.ndarray):
            emb = represent_output.flatten().tolist()
            return emb if len(emb) >= MIN_EMBEDDING_LENGTH else None

        # Case 2: list
        if isinstance(represent_output, list) and len(represent_output) > 0:
            first = represent_output[0]

            # Subcase 2a: List of dicts (standard)
            if isinstance(first, dict) and "embedding" in first:
                emb = first["embedding"]
                if isinstance(emb, np.ndarray):
                    emb = emb.flatten().tolist()
                if isinstance(emb, list) and len(emb) >= MIN_EMBEDDING_LENGTH:
                    return [float(v) for v in emb if self._is_number(v)]
                return None

            # Subcase 2b: List of floats directly (your version does this)
            if self._is_number(first):
                if len(represent_output) >= MIN_EMBEDDING_LENGTH:
                    return [float(v) for v in represent_output if self._is_number(v)]
                return None

        return None

    # -----------------------------
    # Core: Encoding extraction
    # -----------------------------
    async def _extract_encoding(self, image_data: bytes) -> Optional[List[float]]:
        """
        Extract embedding using DeepFace.represent().
        Tries strict detection first, falls back to non-strict if needed.
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
            try:
                represent_output = await run_in_threadpool(
                    DeepFace.represent,
                    img_path=temp_path,
                    model_name=MODEL_NAME,
                    enforce_detection=True,
                )
            except Exception as e:
                print(f"⚠️ Strict detection failed: {e}")
                print("🔄 Retrying with enforce_detection=False...")
                represent_output = await run_in_threadpool(
                    DeepFace.represent,
                    img_path=temp_path,
                    model_name=MODEL_NAME,
                    enforce_detection=False,
                )

            embedding = self._parse_deepface_embedding(represent_output)
            if not embedding:
                print("❌ Could not parse embedding from DeepFace output.")
                return None

            print(f"✅ Embedding extracted successfully! Length={len(embedding)}")
            return embedding

        except Exception as e:
            print(f"❌ Error during face encoding: {e}")
            return None

        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception as e:
                    print(f"⚠️ Could not delete temp file: {e}")

    # -----------------------------
    # Duplicate detection
    # -----------------------------
    async def _check_duplicate_enrollment(self, new_encoding: List[float]) -> Optional[User]:
        existing_users = await self.user_repo.get_all_encodings()

        if not existing_users:
            print("✅ No existing users - enrollment is unique")
            return None

        new_vec = self._l2_normalize(new_encoding)

        best_match = None  # (user, dist)

        for user in existing_users:
            if not user.face_encodings:
                continue

            # Skip mismatched embedding lengths
            if len(user.face_encodings) != len(new_encoding):
                continue

            known_vec = self._l2_normalize(user.face_encodings)
            dist = self._cosine_distance(new_vec, known_vec)

            if best_match is None or dist < best_match[1]:
                best_match = (user, dist)

        if best_match:
            user, dist = best_match
            print(f"🧪 Best duplicate candidate: '{user.name}' cosine_distance={dist:.4f}")

            if dist < DUPLICATE_COSINE_THRESHOLD:
                print(f"⚠️ DUPLICATE DETECTED: matches '{user.name}' (cosine_distance={dist:.4f})")
                return user

        print("✅ Face is unique - no duplicates found")
        return None

    # -----------------------------
    # Enrollment
    # -----------------------------
    async def enroll_user(
        self,
        user_data: UserCreate,
        image_data: bytes
    ) -> Union[UserOut, Dict[str, Any], None]:

        print(f"📸 Extracting face encoding for user: {user_data.name}")
        encoding = await self._extract_encoding(image_data)

        if not encoding:
            print(f"❌ Face detection/encoding failed for {user_data.name}")
            return None

        print("🔍 Checking for duplicate enrollment...")
        duplicate_user = await self._check_duplicate_enrollment(encoding)
        if duplicate_user:
            return {
                "error": "duplicate",
                "message": f"Face already registered as {duplicate_user.name}",
                "existing_user_id": str(duplicate_user.id),
                "existing_user_name": duplicate_user.name,
                "existing_employee_id": duplicate_user.employee_id,
            }

        print("🖼️ Converting image to Base64...")
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        print("💾 Creating user entity...")
        new_user = User(
            name=user_data.name,
            employee_id=user_data.employee_id,
            access_level=user_data.access_level,
            face_encodings=encoding,
            image_base64=image_base64,
        )

        print("📤 Saving user to database...")
        saved_user = await self.user_repo.add_user(new_user)

        print(f"✅ User {user_data.name} enrolled successfully!")
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
        target_encoding = await self._extract_encoding(image_data)
        if not target_encoding:
            return None

        known_users = await self.user_repo.get_all_encodings()
        if not known_users:
            return None

        target_vec = self._l2_normalize(target_encoding)

        best_match = None
        for user in known_users:
            if not user.face_encodings:
                continue

            if len(user.face_encodings) != len(target_encoding):
                continue

            known_vec = self._l2_normalize(user.face_encodings)
            dist = self._cosine_distance(target_vec, known_vec)

            if dist < RECOGNITION_COSINE_THRESHOLD:
                if best_match is None or dist < best_match[1]:
                    best_match = (user, dist)

        if best_match:
            matched_user, dist = best_match
            print(f"✅ Recognition match: {matched_user.name} (cosine_distance={dist:.4f})")
            return UserOut(
                id=str(matched_user.id),
                name=matched_user.name,
                employee_id=matched_user.employee_id,
                access_level=matched_user.access_level,
            )

        return None
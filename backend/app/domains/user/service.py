# backend/app/domains/user/service.py

"""
User Service Layer
Business logic for user enrollment and face recognition

This service implements the core business logic for:
- Face encoding extraction using DeepFace
- User enrollment with duplicate detection
- Face recognition and user search
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

# ------------------------------------------------------------------------------------
# Thresholds / tuning
# ------------------------------------------------------------------------------------

# Minimum length to consider something a real embedding vector
MIN_EMBEDDING_LENGTH = 100

# ✅ New: Cosine thresholds (you can tune these)
# Smaller = stricter (harder to match)
DUPLICATE_COSINE_THRESHOLD = 0.25      # strict: prevents false duplicate registration
RECOGNITION_COSINE_THRESHOLD = 0.35    # a bit looser: recognition/search match


class UserService:
    """
    Service class for user-related business logic.

    Responsibilities:
    - Extract face encodings from images using DeepFace
    - Enroll new users with duplicate detection
    - Search for users by face encoding
    - Manage face recognition operations
    """

    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    # -----------------------------
    # Internal helpers
    # -----------------------------
    def _is_number(self, x: Any) -> bool:
        return isinstance(x, (int, float, np.number))

    def _l2_normalize(self, vec: List[float]) -> np.ndarray:
        """
        L2-normalize embedding vector.
        This makes cosine distance stable and reduces false positives.
        """
        arr = np.array(vec, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm == 0:
            return arr
        return arr / norm

    def _cosine_distance(self, a: np.ndarray, b: np.ndarray) -> float:
        """
        Cosine distance = 1 - cosine similarity.
        Lower distance means more similar.
        """
        return float(1.0 - np.dot(a, b))

    def _parse_deepface_embedding(self, represent_output: Any) -> Optional[List[float]]:
        """
        DeepFace.represent() output varies across versions / forks / wrappers.

        Supported outputs we handle:

        A) List[Dict] like:
           [
             {"embedding": [...], "facial_area": {...}, ...}
           ]

        B) List[float] like:
           [0.00528, 0.12, ...]   <-- embedding vector directly

        C) List[List[float]] like (rare):
           [[...embedding...], [...embedding...]]

        D) np.ndarray embedding
        """
        if represent_output is None:
            return None

        # If numpy array returned, convert to list
        if isinstance(represent_output, np.ndarray):
            emb = represent_output.flatten().tolist()
            return emb if len(emb) >= MIN_EMBEDDING_LENGTH else None

        # If list returned
        if isinstance(represent_output, list) and len(represent_output) > 0:
            first = represent_output[0]

            # A) List of dicts
            if isinstance(first, dict):
                if "embedding" in first:
                    emb = first["embedding"]
                    if isinstance(emb, np.ndarray):
                        emb = emb.flatten().tolist()

                    if isinstance(emb, list) and len(emb) >= MIN_EMBEDDING_LENGTH and all(
                        self._is_number(v) for v in emb
                    ):
                        return [float(v) for v in emb]
                    return None

                print(f"❌ DeepFace dict returned but no 'embedding' key. Keys: {list(first.keys())}")
                return None

            # B) List[float] => embedding vector directly
            if self._is_number(first):
                if all(self._is_number(v) for v in represent_output) and len(represent_output) >= MIN_EMBEDDING_LENGTH:
                    return [float(v) for v in represent_output]
                print(f"❌ DeepFace returned numeric list but too short (len={len(represent_output)}).")
                return None

            # C) List[List[float]]
            if isinstance(first, list):
                if len(first) >= MIN_EMBEDDING_LENGTH and all(self._is_number(v) for v in first):
                    return [float(v) for v in first]
                print("❌ DeepFace returned list-of-lists but inner list is not a valid embedding.")
                return None

            print(f"❌ Unexpected DeepFace output element type: {type(first)}")
            print(f"❌ First element: {first}")
            return None

        # If a single dict returned (rare)
        if isinstance(represent_output, dict) and "embedding" in represent_output:
            emb = represent_output["embedding"]
            if isinstance(emb, np.ndarray):
                emb = emb.flatten().tolist()
            if isinstance(emb, list) and len(emb) >= MIN_EMBEDDING_LENGTH and all(self._is_number(v) for v in emb):
                return [float(v) for v in emb]
            return None

        # If a single float returned, it is NOT an embedding
        if self._is_number(represent_output):
            print(f"❌ DeepFace returned a single number ({represent_output}). Not an embedding.")
            return None

        print(f"❌ Unhandled DeepFace output type: {type(represent_output)}")
        return None

    # -----------------------------
    # Core: Encoding extraction
    # -----------------------------
    async def _extract_encoding(self, image_data: bytes) -> Optional[List[float]]:
        """
        Decode image bytes using OpenCV and extract DeepFace embeddings.

        Flow:
        1) Decode bytes to image
        2) Save temp file (DeepFace expects path)
        3) Call DeepFace.represent (try strict detection; fallback to non-strict)
        4) Parse output robustly (dict embedding OR list-of-floats embedding)
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

            # First attempt: enforce_detection=True (strict)
            try:
                represent_output = await run_in_threadpool(
                    DeepFace.represent,
                    img_path=temp_path,
                    model_name="VGG-Face",
                    enforce_detection=True,
                )
            except Exception as e:
                print(f"⚠️ DeepFace with enforce_detection=True failed: {e}")
                print("🔄 Retrying with enforce_detection=False...")
                represent_output = await run_in_threadpool(
                    DeepFace.represent,
                    img_path=temp_path,
                    model_name="VGG-Face",
                    enforce_detection=False,
                )

            print("✅ Face detected and encoded successfully (DeepFace returned something).")
            print(f"📊 DeepFace output type: {type(represent_output).__name__}")

            embedding = self._parse_deepface_embedding(represent_output)
            if not embedding:
                if isinstance(represent_output, list):
                    print(f"📊 DeepFace list length: {len(represent_output)}")
                    if len(represent_output) > 0:
                        print(f"📊 DeepFace first element type: {type(represent_output[0]).__name__}")
                        print(f"📊 DeepFace first element sample: {represent_output[0]}")
                print("❌ Could not parse embedding from DeepFace output.")
                return None

            print(f"✅ Embedding extracted successfully! Length: {len(embedding)}")
            return embedding

        except Exception as e:
            print(f"❌ Error during face encoding: {e}")
            import traceback
            traceback.print_exc()
            return None

        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    print(f"✅ Cleaned up temp file: {temp_path}")
                except Exception as e:
                    print(f"⚠️ Could not delete temp file: {e}")

    # -----------------------------
    # Duplicate detection (FIXED)
    # -----------------------------
    async def _check_duplicate_enrollment(self, new_encoding: List[float]) -> Optional[User]:
        """
        ✅ FIXED: Duplicate detection using L2-normalized cosine distance.

        Why:
        - Euclidean distance on raw VGG-Face embeddings can be too permissive (false duplicates).
        - Cosine distance on normalized embeddings is much more reliable.
        """
        existing_users = await self.user_repo.get_all_encodings()

        if not existing_users:
            print("✅ No existing users in database - enrollment is unique")
            return None

        new_vec = self._l2_normalize(new_encoding)

        best_match = None  # (user, cosine_distance)

        for user in existing_users:
            if not user.face_encodings:
                continue

            # Skip if encoding sizes differ (old corrupted DB entries)
            if len(user.face_encodings) != len(new_encoding):
                print(
                    f"⚠️ Skipping user '{user.name}' due to encoding shape mismatch: "
                    f"({len(user.face_encodings)},) vs ({len(new_encoding)},)"
                )
                continue

            known_vec = self._l2_normalize(user.face_encodings)
            dist = self._cosine_distance(new_vec, known_vec)

            if best_match is None or dist < best_match[1]:
                best_match = (user, dist)

        if best_match:
            user, dist = best_match
            print(f"🧪 Best duplicate candidate: '{user.name}' cosine_distance={dist:.4f}")

            if dist < DUPLICATE_COSINE_THRESHOLD:
                print(f"⚠️ DUPLICATE DETECTED: matches '{user.name}' (cosine_distance: {dist:.4f})")
                return user

        print("✅ Face is unique - no duplicates found")
        return None

    # -----------------------------
    # Public API: Enrollment / Search
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
            print("❌ Enrollment rejected: Duplicate face detected")
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

    async def search_user(self, image_data: bytes) -> Optional[UserOut]:
        """
        ✅ FIXED: Recognition using L2-normalized cosine distance.
        """
        target_encoding = await self._extract_encoding(image_data)
        if not target_encoding:
            return None

        known_users = await self.user_repo.get_all_encodings()
        if not known_users:
            return None

        target_vec = self._l2_normalize(target_encoding)

        best_match = None  # (user, cosine_distance)

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
            matched_user = best_match[0]
            print(f"✅ Recognition match: {matched_user.name} (cosine_distance={best_match[1]:.4f})")
            return UserOut(
                id=str(matched_user.id),
                name=matched_user.name,
                employee_id=matched_user.employee_id,
                access_level=matched_user.access_level,
            )

        return None
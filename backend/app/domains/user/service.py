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

# DeepFace match threshold for face recognition
VERIFICATION_THRESHOLD = 0.6

# VGG-Face embedding size is 2622 in DeepFace (often), but sometimes 4096/512 depending on pipeline/model.
# We just need “reasonably large” to distinguish from a single float, etc.
MIN_EMBEDDING_LENGTH = 100


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

                # Some forks might use different key naming; print keys for debugging
                print(f"❌ DeepFace dict returned but no 'embedding' key. Keys: {list(first.keys())}")
                return None

            # B) List[float] => embedding vector directly
            if self._is_number(first):
                # ensure the whole list is numeric
                if all(self._is_number(v) for v in represent_output) and len(represent_output) >= MIN_EMBEDDING_LENGTH:
                    return [float(v) for v in represent_output]
                # if it’s numeric but too short, it’s not a valid embedding
                print(f"❌ DeepFace returned numeric list but too short (len={len(represent_output)}).")
                return None

            # C) List[List[float]] (multiple faces embeddings, or wrapper output)
            if isinstance(first, list):
                # If first is a list of numbers and long enough, treat it as embedding for first face
                if len(first) >= MIN_EMBEDDING_LENGTH and all(self._is_number(v) for v in first):
                    return [float(v) for v in first]
                print("❌ DeepFace returned list-of-lists but inner list is not a valid embedding.")
                return None

            # Anything else is unexpected
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
                # Extra debug to help if it still fails
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
    # Duplicate detection
    # -----------------------------
    async def _check_duplicate_enrollment(self, new_encoding: List[float]) -> Optional[User]:
        """
        Check if a face encoding already exists in the system (duplicate detection).
        Uses Euclidean distance with VERIFICATION_THRESHOLD.
        """
        existing_users = await self.user_repo.get_all_encodings()

        if not existing_users:
            print("✅ No existing users in database - enrollment is unique")
            return None

        new_encoding_np = np.array(new_encoding, dtype=np.float32)

        for user in existing_users:
            if not user.face_encodings:
                continue

            known_encoding_np = np.array(user.face_encodings, dtype=np.float32)

            # Safety: skip if encoding sizes differ (corrupt / mismatched model)
            if known_encoding_np.shape != new_encoding_np.shape:
                print(
                    f"⚠️ Skipping user '{user.name}' due to encoding shape mismatch: "
                    f"{known_encoding_np.shape} vs {new_encoding_np.shape}"
                )
                continue

            distance = np.linalg.norm(new_encoding_np - known_encoding_np)

            if distance < VERIFICATION_THRESHOLD:
                print(f"⚠️ DUPLICATE DETECTED: matches '{user.name}' (distance: {distance:.4f})")
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
        """
        Enroll a new user with duplicate detection.
        """
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
        Match the face embedding against all saved users.
        """
        target_encoding = await self._extract_encoding(image_data)
        if not target_encoding:
            return None

        known_users = await self.user_repo.get_all_encodings()
        if not known_users:
            return None

        target_encoding_np = np.array(target_encoding, dtype=np.float32)

        best_match = None  # (user, distance)

        for user in known_users:
            if not user.face_encodings:
                continue

            known_encoding_np = np.array(user.face_encodings, dtype=np.float32)

            if known_encoding_np.shape != target_encoding_np.shape:
                continue

            distance = np.linalg.norm(target_encoding_np - known_encoding_np)
            if distance < VERIFICATION_THRESHOLD:
                if best_match is None or distance < best_match[1]:
                    best_match = (user, distance)

        if best_match:
            matched_user = best_match[0]
            return UserOut(
                id=str(matched_user.id),
                name=matched_user.name,
                employee_id=matched_user.employee_id,
                access_level=matched_user.access_level,
            )

        return None
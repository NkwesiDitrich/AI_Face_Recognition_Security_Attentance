"""
User Service Layer
Business logic for user enrollment and face recognition
"""

from typing import Optional, List
import numpy as np
import cv2
import os
import tempfile
from deepface import DeepFace
from fastapi.concurrency import run_in_threadpool

from app.domains.user.models import User
from app.domains.user.schemas import UserCreate, UserOut
from app.domains.user.repository import UserRepository

# DeepFace match threshold
VERIFICATION_THRESHOLD = 0.6


class UserService:
    """Service class for user-related business logic"""

    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    async def _extract_encoding(self, image_data: bytes) -> Optional[List[float]]:
        """
        Decode image bytes using OpenCV and extract DeepFace embeddings
        ASYNCHRONOUSLY using run_in_threadpool.
        Works on both Windows and Linux.
        """

        temp_path = None
        try:
            # 1. Convert bytes to NumPy array
            nparr = np.frombuffer(image_data, np.uint8)

            # 2. Decode image using OpenCV
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                print("❌ OpenCV failed to decode image.")
                return None

            # 3. Save to temp file (Windows & Linux compatible)
            # Create a temporary file in the system's temp directory
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                temp_path = tmp_file.name
            
            # Write the image to the temp file
            success = cv2.imwrite(temp_path, img)
            if not success:
                print(f"❌ Failed to write image to {temp_path}")
                return None

            print(f"✅ Image saved to: {temp_path}")

            # 4. Run DeepFace in a thread (IMPORTANT FIX)
            embedding_objs = await run_in_threadpool(
                DeepFace.represent,
                img_path=temp_path,
                model_name="VGG-Face",
                enforce_detection=False
            )

            # 5. Return the embedding
            if embedding_objs and len(embedding_objs) > 0:
                print(f"✅ Face detected and encoded successfully")
                return embedding_objs[0]["embedding"]

            print("❌ DeepFace could not detect a face.")
            return None

        except Exception as e:
            print(f"❌ Error during face encoding: {e}")
            return None
        
        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    print(f"✅ Cleaned up temp file: {temp_path}")
                except Exception as e:
                    print(f"⚠️ Could not delete temp file: {e}")

    async def enroll_user(self, user_data: UserCreate, image_data: bytes) -> Optional[UserOut]:
        """
        Store new user with extracted face embedding
        """
        encoding = await self._extract_encoding(image_data)

        if not encoding:
            return None  # face not detected

        new_user = User(
            name=user_data.name,
            employee_id=user_data.employee_id,
            access_level=user_data.access_level,
            face_encodings=encoding,
        )

        saved_user = await self.user_repo.add_user(new_user)

        return UserOut(
            id=str(saved_user.id),
            name=saved_user.name,
            employee_id=saved_user.employee_id,
            access_level=saved_user.access_level,
        )

    async def search_user(self, image_data: bytes) -> Optional[UserOut]:
        """
        Match the face embedding against all saved users
        """
        target_encoding = await self._extract_encoding(image_data)

        if not target_encoding:
            return None

        known_users = await self.user_repo.get_all_encodings()
        if not known_users:
            return None

        target_encoding_np = np.array(target_encoding)

        best_match = None  # (user, distance)

        for user in known_users:
            if not user.face_encodings:
                continue

            known_encoding_np = np.array(user.face_encodings)

            # Euclidean distance
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
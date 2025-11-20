"""
User Service Layer
Business logic for user enrollment and face recognition
"""

import numpy as np
from typing import Optional, List
from deepface import DeepFace
import cv2
import numpy as np

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
        Decode image bytes using OpenCV and extract DeepFace embeddings.
        This FIXES enrollment failures caused by PIL.
        """
        try:
            # 1. Convert bytes → NumPy array
            nparr = np.frombuffer(image_data, np.uint8)

            # 2. Decode with OpenCV (PIL is unreliable for DeepFace)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                print("❌ OpenCV failed to decode image.")
                return None

            # 3. Save temporary file for DeepFace
            temp_path = "/tmp/temp_face.jpg"
            cv2.imwrite(temp_path, img)

            # 4. Extract embedding
            embedding_objs = DeepFace.represent(
                img_path=temp_path,
                model_name="VGG-Face",
                enforce_detection=True
            )

            if embedding_objs and len(embedding_objs) > 0:
                return embedding_objs[0]["embedding"]

            print("❌ DeepFace could not detect a face.")
            return None

        except Exception as e:
            print(f"❌ Error during face encoding: {e}")
            return None

    async def enroll_user(self, user_data: UserCreate, image_data: bytes) -> Optional[UserOut]:
        encoding = await self._extract_encoding(image_data)

        if not encoding:
            return None  # Face not detected

        new_user = User(
            name=user_data.name,
            employee_id=user_data.employee_id,
            access_level=user_data.access_level,
            face_encodings=encoding
        )

        saved_user = await self.user_repo.add_user(new_user)

        return UserOut(
            id=str(saved_user.id),
            name=saved_user.name,
            employee_id=saved_user.employee_id,
            access_level=saved_user.access_level
        )

    async def search_user(self, image_data: bytes) -> Optional[UserOut]:
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
                access_level=matched_user.access_level
            )

        return None

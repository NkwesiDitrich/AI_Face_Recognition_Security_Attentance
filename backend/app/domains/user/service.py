"""
User Service Layer
Business logic for user enrollment and face recognition
"""

import numpy as np
from typing import Optional, List
from deepface import DeepFace
import io
from PIL import Image

from app.domains.user.models import User
from app.domains.user.schemas import UserCreate, UserOut
from app.domains.user.repository import UserRepository


# DeepFace match threshold
VERIFICATION_THRESHOLD = 0.6


class UserService:
    """Service class for user-related business logic"""
    
    def __init__(self, user_repo: UserRepository):
        """
        Initialize UserService with repository dependency
        
        Args:
            user_repo: UserRepository instance for database operations
        """
        self.user_repo = user_repo

    async def _extract_encoding(self, image_data: bytes) -> Optional[List[float]]:
        """
        Internal method to extract face encoding from image data using DeepFace.
        
        Args:
            image_data: Image file as bytes
            
        Returns:
            List of floats representing face encoding, or None if face not detected
        """
        try:
            # 1. Load image from bytes
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Save to temporary location for DeepFace processing
            temp_path = "/tmp/temp_face.jpg"
            image.save(temp_path)
            
            # 2. Extract face and get encoding using DeepFace
            embedding_objs = DeepFace.represent(
                img_path=temp_path,
                model_name="VGG-Face",
                enforce_detection=True
            )
            
            # Assuming one face is detected for enrollment
            if embedding_objs and len(embedding_objs) > 0:
                return embedding_objs[0]['embedding']
            
            return None
            
        except Exception as e:
            # Log the error (e.g., face not detected)
            print(f"Error during face encoding: {e}")
            return None

    async def enroll_user(self, user_data: UserCreate, image_data: bytes) -> Optional[UserOut]:
        """
        Business logic for user enrollment (extracts encoding and saves to DB).
        
        Args:
            user_data: UserCreate schema with user information
            image_data: Image file as bytes
            
        Returns:
            UserOut schema with created user, or None if face not detected
        """
        encoding = await self._extract_encoding(image_data)
        
        if not encoding:
            return None  # Face not found or error
        
        # Create the User entity
        new_user = User(
            name=user_data.name,
            employee_id=user_data.employee_id,
            access_level=user_data.access_level,
            face_encodings=encoding
        )
        
        # Save to database via repository
        saved_user = await self.user_repo.add_user(new_user)
        
        # Convert to UserOut schema
        return UserOut(
            id=str(saved_user.id),
            name=saved_user.name,
            employee_id=saved_user.employee_id,
            access_level=saved_user.access_level
        )

    async def search_user(self, image_data: bytes) -> Optional[UserOut]:
        """
        Business logic for searching and recognizing a user from an image.
        
        Args:
            image_data: Image file as bytes
            
        Returns:
            UserOut schema with matched user, or None if no match found
        """
        target_encoding = await self._extract_encoding(image_data)
        
        if not target_encoding:
            return None  # Face not found in the search image

        # 1. Get all known encodings from the database
        known_users = await self.user_repo.get_all_encodings()
        
        if not known_users:
            return None  # No users enrolled
        
        target_encoding_np = np.array(target_encoding)
        
        best_match: Optional[tuple] = None  # (User, distance)
        
        # 2. Compare the target encoding against all known encodings
        for user in known_users:
            if not user.face_encodings:
                continue
                
            known_encoding_np = np.array(user.face_encodings)
            
            # Calculate distance (Euclidean distance is common for VGG-Face)
            distance = np.linalg.norm(target_encoding_np - known_encoding_np)
            
            if distance < VERIFICATION_THRESHOLD:
                # Check if this is the best match so far (lowest distance)
                if best_match is None or distance < best_match[1]:
                    best_match = (user, distance)

        if best_match:
            # Found a match, retrieve the full user details
            matched_user = best_match[0]
            return UserOut(
                id=str(matched_user.id),
                name=matched_user.name,
                employee_id=matched_user.employee_id,
                access_level=matched_user.access_level
            )
        
        return None  # No match found within the threshold
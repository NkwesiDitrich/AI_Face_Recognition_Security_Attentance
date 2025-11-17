import numpy as np
from typing import Optional, Tuple
from deepface import DeepFace
from deepface.commons import functions

from app.domains.user.models import User, UserCreate, UserOut
from app.domains.user.repository import UserRepository


# DeepFace match threshold
VERIFICATION_THRESHOLD = 0.6


async def _extract_encoding(self, image_data: bytes) -> Optional[List[float]]:
    """
    Internal method to extract face encoding from image data using DeepFace.
    """
    try:
        # 1. Load image from bytes
        # --- FIX: Use the correctly imported load_image function ---
        img = load_image(image_data, grayscale=False)
        # ---------------------------------------------------------
        
        # 2. Extract face and get encoding
        embedding_objs = DeepFace.represent(
            img_path=img, 
            model_name="VGG-Face", 
            enforce_detection=True
        )
        
        # Assuming one face is detected for enrollment
        if embedding_objs:
            return embedding_objs[0]['embedding']
        
        return None
    except Exception as e:
        # Log the error (e.g., face not detected)
        print(f"Error during face encoding: {e}")
        return None

async def enroll_user(self, user_data: UserCreate, image_data: bytes) -> Optional[User]:
    """
    Business logic for user enrollment (extracts encoding and saves to DB).
    """
    encoding = await self._extract_encoding(image_data)
    
    if not encoding:
        return None # Face not found or error
        
    # Create the User entity
    new_user = User(
        name=user_data.name,
        employee_id=user_data.employee_id,
        access_level=user_data.access_level,
        face_encodings=encoding
    )
    
    # Save to database via repository
    return await self.user_repo.add_user(new_user)

async def search_user(self, image_data: bytes) -> Optional[UserOut]:
    """
    Business logic for searching and recognizing a user from an image.
    """
    target_encoding = await self._extract_encoding(image_data)
    
    if not target_encoding:
        return None # Face not found in the search image

    # 1. Get all known encodings from the database
    known_users = await self.user_repo.get_all_encodings()
    
    if not known_users:
        return None # No users enrolled
        
    target_encoding_np = np.array(target_encoding)
    
    best_match: Optional[Tuple[User, float]] = None # (User, distance)
    
    # 2. Compare the target encoding against all known encodings
    for user in known_users:
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
        
    return None # No match found within the threshold

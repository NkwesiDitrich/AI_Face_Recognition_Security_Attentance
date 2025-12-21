# backend/app/domains/user/service.py

"""
User Service Layer
Business logic for user enrollment and face recognition

This service implements the core business logic for:
- Face encoding extraction using DeepFace
- User enrollment with duplicate detection
- Face recognition and user search
"""

from typing import Optional, List, Union, Dict
import numpy as np
import cv2
import os
import tempfile
from deepface import DeepFace
from fastapi.concurrency import run_in_threadpool
import base64

from app.domains.user.models import User
from app.domains.user.schemas import UserCreate, UserOut
from app.domains.user.repository import UserRepository

# DeepFace match threshold for face recognition
# Distance < 0.6 means faces are similar enough to be considered a match
VERIFICATION_THRESHOLD = 0.6


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
        """
        Initialize UserService with a UserRepository dependency.
        
        Args:
            user_repo: UserRepository instance for database operations
        """
        self.user_repo = user_repo

    async def _extract_encoding(self, image_data: bytes) -> Optional[List[float]]:
        """
        Decode image bytes using OpenCV and extract DeepFace embeddings.
        
        This method:
        1. Converts raw image bytes to a NumPy array
        2. Decodes the image using OpenCV
        3. Saves to a temporary file (required by DeepFace)
        4. Extracts face encoding using DeepFace VGG-Face model
        5. Cleans up temporary files
        
        The operation runs asynchronously in a thread pool to avoid blocking.
        
        Args:
            image_data: Raw image bytes from the uploaded file
            
        Returns:
            List[float]: Face encoding vector (512 dimensions for VGG-Face)
            None: If face cannot be detected or encoding fails
        """

        temp_path = None
        try:
            # 1. Convert bytes to NumPy array
            # This creates an in-memory representation of the image
            nparr = np.frombuffer(image_data, np.uint8)

            # 2. Decode image using OpenCV
            # cv2.IMREAD_COLOR loads image in BGR format
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                print("❌ OpenCV failed to decode image.")
                return None

            # 3. Save to temp file (Windows & Linux compatible)
            # DeepFace requires a file path, not in-memory data
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                temp_path = tmp_file.name
            
            # Write the decoded image to the temp file
            success = cv2.imwrite(temp_path, img)
            if not success:
                print(f"❌ Failed to write image to {temp_path}")
                return None

            print(f"✅ Image saved to: {temp_path}")

            # 4. Run DeepFace in a thread pool to avoid blocking
            # VGG-Face model produces 512-dimensional embeddings
            # enforce_detection=False allows processing even if face detection is uncertain
            embedding_objs = await run_in_threadpool(
                DeepFace.represent,
                img_path=temp_path,
                model_name="VGG-Face",
                enforce_detection=False
            )

            # 5. Return the embedding vector
            if embedding_objs and len(embedding_objs) > 0:
                print(f"✅ Face detected and encoded successfully")
                return embedding_objs[0]["embedding"]

            print("❌ DeepFace could not detect a face.")
            return None

        except Exception as e:
            print(f"❌ Error during face encoding: {e}")
            return None
        
        finally:
            # Clean up temp file to avoid disk space issues
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    print(f"✅ Cleaned up temp file: {temp_path}")
                except Exception as e:
                    print(f"⚠️ Could not delete temp file: {e}")

    async def _check_duplicate_enrollment(self, new_encoding: List[float]) -> Optional[User]:
        """
        ✨ NEW METHOD: Check if a face encoding already exists in the system (duplicate detection).
        
        This method prevents:
        - Same person registering multiple times
        - Fraud attempts (same face with different names/IDs)
        - Data integrity issues
        
        Algorithm:
        1. Fetch all existing users with their face encodings
        2. Compare new encoding against each existing encoding
        3. Calculate Euclidean distance between vectors
        4. If distance < VERIFICATION_THRESHOLD (0.6), it's a match
        5. Return the matching user if found
        
        Args:
            new_encoding: Face encoding vector from the new enrollment attempt
            
        Returns:
            User: The existing user if a duplicate is found
            None: If no duplicate exists (enrollment is unique)
        """
        
        # Fetch all existing users with their encodings
        existing_users = await self.user_repo.get_all_encodings()
        
        if not existing_users:
            # No existing users, so no duplicates possible
            print("✅ No existing users in database - enrollment is unique")
            return None
        
        # Convert new encoding to NumPy array for distance calculation
        new_encoding_np = np.array(new_encoding)
        
        # Compare against all existing users
        for user in existing_users:
            # Skip users without face encodings (shouldn't happen, but be safe)
            if not user.face_encodings:
                continue
            
            # Convert existing encoding to NumPy array
            existing_encoding_np = np.array(user.face_encodings)
            
            # Calculate Euclidean distance between the two vectors
            # Lower distance = more similar faces
            distance = np.linalg.norm(new_encoding_np - existing_encoding_np)
            
            # If distance is below threshold, it's a match (duplicate found)
            if distance < VERIFICATION_THRESHOLD:
                print(f"⚠️ DUPLICATE DETECTED: Face matches existing user '{user.name}' (distance: {distance:.4f})")
                return user  # Return the matching user
        
        # No duplicates found
        print(f"✅ Face is unique - no duplicates found")
        return None

    async def enroll_user(
        self, 
        user_data: UserCreate, 
        image_data: bytes
    ) -> Union[UserOut, Dict[str, any], None]:
        """
        Enroll a new user with face recognition and duplicate detection.
        
        This is the main enrollment workflow:
        1. Extract face encoding from the image
        2. Check if face already exists (duplicate detection)
        3. If duplicate found, return error response
        4. If unique, convert image to Base64 and save to database
        5. Return success response with user details
        
        Args:
            user_data: UserCreate schema with name, employee_id, access_level
            image_data: Raw image bytes from the uploaded file
            
        Returns:
            UserOut: Successfully enrolled user details (on success)
            Dict: Error response with duplicate information (on duplicate)
            None: If face cannot be detected in image
        """
        
        # Step 1: Extract face encoding from the image
        print(f"📸 Extracting face encoding for user: {user_data.name}")
        encoding = await self._extract_encoding(image_data)

        if not encoding:
            # Face not detected - return None to signal error
            print(f"❌ Face detection failed for {user_data.name}")
            return None

        # Step 2: ✨ NEW - Check for duplicate enrollment
        print(f"🔍 Checking for duplicate enrollment...")
        duplicate_user = await self._check_duplicate_enrollment(encoding)
        
        if duplicate_user:
            # Duplicate found - return error response
            # API layer will convert this to HTTP 409 Conflict
            print(f"❌ Enrollment rejected: Duplicate face detected")
            return {
                "error": "duplicate",
                "message": f"Face already registered as {duplicate_user.name}",
                "existing_user_id": str(duplicate_user.id),
                "existing_user_name": duplicate_user.name,
                "existing_employee_id": duplicate_user.employee_id
            }

        # Step 3: Convert raw image bytes to Base64 string
        # This allows admin to view the enrolled image later
        print(f"🖼️ Converting image to Base64...")
        image_base64 = base64.b64encode(image_data).decode('utf-8')

        # Step 4: Create User entity with all data
        print(f"💾 Creating user entity...")
        new_user = User(
            name=user_data.name,
            employee_id=user_data.employee_id,
            access_level=user_data.access_level,
            face_encodings=encoding,
            image_base64=image_base64,  # Store Base64 image for admin display
        )

        # Step 5: Save user to database
        print(f"📤 Saving user to database...")
        saved_user = await self.user_repo.add_user(new_user)

        # Step 6: Return success response
        print(f"✅ User {user_data.name} enrolled successfully!")
        return UserOut(
            id=str(saved_user.id),
            name=saved_user.name,
            employee_id=saved_user.employee_id,
            access_level=saved_user.access_level,
        )

    async def search_user(self, image_data: bytes) -> Optional[UserOut]:
        """
        Search for a user by face encoding (used for attendance).
        
        This method:
        1. Extracts face encoding from the provided image
        2. Compares against all enrolled users
        3. Returns the best match if found
        
        Args:
            image_data: Raw image bytes from the camera/upload
            
        Returns:
            UserOut: The matched user details
            None: If no match found or face cannot be detected
        """
        
        # Extract encoding from the search image
        target_encoding = await self._extract_encoding(image_data)

        if not target_encoding:
            return None

        # Get all enrolled users
        known_users = await self.user_repo.get_all_encodings()
        if not known_users:
            return None

        target_encoding_np = np.array(target_encoding)

        best_match = None  # (user, distance)

        # Compare against all enrolled users
        for user in known_users:
            if not user.face_encodings:
                continue

            known_encoding_np = np.array(user.face_encodings)

            # Calculate Euclidean distance
            distance = np.linalg.norm(target_encoding_np - known_encoding_np)

            # If distance is below threshold and better than previous match
            if distance < VERIFICATION_THRESHOLD:
                if best_match is None or distance < best_match[1]:
                    best_match = (user, distance)

        # Return the best match if found
        if best_match:
            matched_user = best_match[0]
            return UserOut(
                id=str(matched_user.id),
                name=matched_user.name,
                employee_id=matched_user.employee_id,
                access_level=matched_user.access_level,
            )

        return None
"""
User API Endpoints (v1)

This module defines the REST API endpoints for user enrollment and face recognition.
It handles HTTP requests and responses, delegating business logic to UserService.

Endpoints:
- POST /enroll - Enroll a new user with face recognition
- POST /search - Search for a user by face encoding
"""

from fastapi import APIRouter, Depends, Form, File, UploadFile, status, HTTPException
from app.domains.user.schemas import UserCreate, UserOut
from app.domains.user.service import UserService
from app.dependencies import get_user_service

# Create router for user endpoints
router = APIRouter()


@router.post("/enroll", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def enroll_user_endpoint(
    name: str = Form(...),
    employee_id: str = Form(...),
    access_level: str = Form("employee"),
    file: UploadFile = File(...),
    user_service: UserService = Depends(get_user_service)
):
    """
    Enroll a new user with face recognition and duplicate detection.
    
    This endpoint:
    1. Receives user data (name, employee_id, access_level) and an image file
    2. Calls UserService.enroll_user() to process the enrollment
    3. Handles three possible outcomes:
       - Success: Returns 201 Created with user details
       - Face not detected: Returns 400 Bad Request
       - Duplicate found: Returns 409 Conflict
    
    Request:
        - name (str): User's full name
        - employee_id (str): Unique employee identifier
        - access_level (str): Access level (default: "employee")
        - file (UploadFile): Image file containing the user's face
    
    Responses:
        - 201 Created: User enrolled successfully
        - 400 Bad Request: Face not detected in image
        - 409 Conflict: Face already registered (duplicate)
    
    Example:
        POST /api/v1/enroll
        Content-Type: multipart/form-data
        
        name=John Doe
        employee_id=EMP001
        access_level=employee
        file=<image_file>
    """
    
    # Read image file bytes
    print(f"📥 Received enrollment request for: {name}")
    image_bytes = await file.read()
    print(f"📦 Image size: {len(image_bytes)} bytes")

    # Create UserCreate schema with form data
    user_data = UserCreate(
        name=name,
        employee_id=employee_id,
        access_level=access_level
    )

    # Call service layer to process enrollment
    print(f"🔄 Processing enrollment in service layer...")
    result = await user_service.enroll_user(user_data, image_bytes)

    # Handle face not detected error
    if not result:
        print(f"❌ Enrollment failed: Face not detected")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Face not detected in the image. Please try again with a clear face photo."
        )

    # ✨ NEW: Handle duplicate detection error
    # If result is a dict with "error" key, it's a duplicate
    if isinstance(result, dict) and result.get("error") == "duplicate":
        print(f"❌ Enrollment rejected: Duplicate face detected")
        print(f"   Existing user: {result.get('existing_user_name')} ({result.get('existing_employee_id')})")
        
        # Return 409 Conflict status code
        # This indicates the request conflicts with existing data
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "duplicate_face",
                "message": f"Face already registered as {result.get('existing_user_name')}",
                "existing_user_id": result.get("existing_user_id"),
                "existing_user_name": result.get("existing_user_name"),
                "existing_employee_id": result.get("existing_employee_id")
            }
        )

    # Success: Return the enrolled user
    print(f"✅ Enrollment successful for: {name}")
    return result


@router.post("/search")
async def search_user_endpoint(
    file: UploadFile = File(...),
    user_service: UserService = Depends(get_user_service)
):
    """
    Search for a user by face encoding (used for attendance tracking).
    
    This endpoint:
    1. Receives an image file containing a face
    2. Calls UserService.search_user() to find matching user
    3. Returns the matched user or 404 if no match found
    
    Request:
        - file (UploadFile): Image file containing a face
    
    Responses:
        - 200 OK: User found, returns user details
        - 400 Bad Request: Face not detected in image
        - 404 Not Found: No matching user found
    
    Example:
        POST /api/v1/search
        Content-Type: multipart/form-data
        
        file=<image_file>
    """
    
    # Read image file bytes
    print(f"📥 Received search request")
    image_bytes = await file.read()
    print(f"📦 Image size: {len(image_bytes)} bytes")

    # Call service layer to search for user
    print(f"🔄 Searching for user in service layer...")
    result = await user_service.search_user(image_bytes)

    # Handle face not detected error
    if result is None:
        print(f"❌ Search failed: Face not detected or no match found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching user found. Face not detected or user not enrolled."
        )

    # Success: Return the matched user
    print(f"✅ User found: {result.name}")
    return result
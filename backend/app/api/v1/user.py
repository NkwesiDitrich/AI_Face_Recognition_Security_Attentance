from fastapi import APIRouter, Depends, Form, File, UploadFile, status
from app.domains.user.schemas import UserCreate, UserOut
from app.domains.user.service import UserService
from app.dependencies import get_user_service

router = APIRouter()

@router.post("/enroll", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def enroll_user_endpoint(
    name: str = Form(...),
    employee_id: str = Form(...),
    access_level: str = Form("employee"),
    file: UploadFile = File(...),
    user_service: UserService = Depends(get_user_service)
):
    """Handles user enrollment with an uploaded face image."""

    image_bytes = await file.read()

    user_data = UserCreate(
        name=name,
        employee_id=employee_id,
        access_level=access_level
    )

    result = await user_service.enroll_user(user_data, image_bytes)

    if not result:
        return {"error": "Face not detected"}

    return result

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domains.user.models import UserCreate, UserOut
from app.domains.user.service import UserService
from app.domains.user.repository import UserRepository
from app.core.database import get_database


router = APIRouter()


# -----------------------------
# Dependencies (DI pattern)
# -----------------------------
def get_user_repository(db: AsyncIOMotorDatabase = Depends(get_database)):
    return UserRepository(db)


def get_user_service(repo: UserRepository = Depends(get_user_repository)):
    return UserService(repo)


# -----------------------------
# ENROLL USER
# -----------------------------
@router.post("/enroll", response_model=UserOut, status_code=status.HTTP_201_CREATED, tags=["User"])
async def enroll_user_endpoint(
    name: str,
    employee_id: str,
    access_level: str = "employee",
    file: UploadFile = File(...),
    user_service: UserService = Depends(get_user_service)
):
    user_data = UserCreate(name=name, employee_id=employee_id, access_level=access_level)
    image_data = await file.read()

    new_user = await user_service.enroll_user(user_data, image_data)

    if new_user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Face not detected or error during encoding."
        )

    return new_user


# -----------------------------
# SEARCH USER
# -----------------------------
@router.post("/search", response_model=UserOut, tags=["User"])
async def search_user_endpoint(
    file: UploadFile = File(...),
    user_service: UserService = Depends(get_user_service)
):
    image_data = await file.read()

    matched_user = await user_service.search_user(image_data)

    if matched_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No matching user found."
        )

    return matched_user

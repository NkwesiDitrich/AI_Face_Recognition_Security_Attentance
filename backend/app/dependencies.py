from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.database import get_database  # Import the function, not the variable
from app.domains.user.repository import UserRepository
from app.domains.user.service import UserService
from app.domains.attendance.repository import AttendanceRepository
from app.domains.attendance.service import AttendanceService

# Dependency Injection Functions

# ✅ FIXED: Use Depends() for all dependencies

def get_user_repository(db: AsyncIOMotorDatabase = Depends(get_database)) -> UserRepository:
    """Returns a User Repository instance."""
    return UserRepository(db)


def get_user_service(user_repo: UserRepository = Depends(get_user_repository)) -> UserService:
    """Returns a User Service instance."""
    return UserService(user_repo)


def get_attendance_repository(db: AsyncIOMotorDatabase = Depends(get_database)) -> AttendanceRepository:
    """Returns an Attendance Repository instance."""
    return AttendanceRepository(db)


def get_attendance_service(
    attendance_repo: AttendanceRepository = Depends(get_attendance_repository),
    user_service: UserService = Depends(get_user_service)
) -> AttendanceService:
    """Returns an Attendance Service instance."""
    return AttendanceService(attendance_repo, user_service)
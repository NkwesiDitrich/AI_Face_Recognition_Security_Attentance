from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.database import database
from app.domains.user.repository import UserRepository
from app.domains.user.service import UserService
from app.domains.attendance.repository import AttendanceRepository
from app.domains.attendance.service import AttendanceService

# Dependency Injection Functions

def get_database() -> AsyncIOMotorDatabase:
    """Returns the MongoDB database instance."""
    return database

def get_user_repository(db: AsyncIOMotorDatabase = get_database()) -> UserRepository:
    """Returns a User Repository instance."""
    return UserRepository(db)

def get_user_service(user_repo: UserRepository = get_user_repository()) -> UserService:
    """Returns a User Service instance."""
    return UserService(user_repo)

def get_attendance_repository(db: AsyncIOMotorDatabase = get_database()) -> AttendanceRepository:
    """Returns an Attendance Repository instance."""
    return AttendanceRepository(db)

def get_attendance_service(
    attendance_repo: AttendanceRepository = get_attendance_repository(),
    user_service: UserService = get_user_service()
) -> AttendanceService:
    """Returns an Attendance Service instance."""
    return AttendanceService(attendance_repo, user_service)

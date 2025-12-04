from app.domains.user.service import UserService
from app.domains.user.repository import UserRepository
from app.core.database import get_database

def get_user_service() -> UserService:
    """
    Dependency injection for UserService.
    Automatically creates UserRepository with the database connection.
    """
    db = get_database()
    user_repo = UserRepository(db)
    return UserService(user_repo)
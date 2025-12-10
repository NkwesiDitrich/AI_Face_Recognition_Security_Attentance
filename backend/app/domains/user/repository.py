from typing import List, Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.domains.user.models import User


class UserRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        # ✅ FIXED: Use bracket notation instead of get_collection()
        self.collection = db["users"]

    async def add_user(self, user: User) -> User:
        user_dict = user.dict(by_alias=True)
        result = await self.collection.insert_one(user_dict)

        new_user = await self.collection.find_one({"_id": result.inserted_id})
        return User(**new_user)

    async def get_all_encodings(self) -> List[User]:
        users = []
        async for doc in self.collection.find({}, {"name": 1, "employee_id": 1, "face_encodings": 1}):
            users.append(User(**doc))
        return users

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        if not ObjectId.is_valid(user_id):
            return None

        doc = await self.collection.find_one({"_id": ObjectId(user_id)})
        if doc:
            return User(**doc)
        return None

    async def update_user(self, user_id: str, data: dict) -> bool:
        """Update user information."""
        if not ObjectId.is_valid(user_id):
            return False
        
        result = await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": data}
        )
        return result.modified_count > 0

    async def delete_user(self, user_id: str) -> bool:
        """Delete a user."""
        if not ObjectId.is_valid(user_id):
            return False
        
        result = await self.collection.delete_one({"_id": ObjectId(user_id)})
        return result.deleted_count > 0
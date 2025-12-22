from typing import List, Optional
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.domains.user.models import User


class UserRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["users"]

    async def add_user(self, user: User) -> User:
        # ✅ Use Pydantic v2-safe dump and exclude None so _id isn't inserted as null
        user_dict = user.model_dump(by_alias=True, exclude_none=True)

        # Extra safety
        if user_dict.get("_id") is None:
            user_dict.pop("_id", None)

        result = await self.collection.insert_one(user_dict)
        doc = await self.collection.find_one({"_id": result.inserted_id})

        # ✅ doc["_id"] is ObjectId — User model now supports it
        return User(**doc)

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
        if not ObjectId.is_valid(user_id):
            return False

        result = await self.collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": data}
        )
        return result.modified_count > 0

    async def delete_user(self, user_id: str) -> bool:
        if not ObjectId.is_valid(user_id):
            return False

        result = await self.collection.delete_one({"_id": ObjectId(user_id)})
        return result.deleted_count > 0
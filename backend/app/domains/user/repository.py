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
        """Get user by MongoDB _id (ObjectId)"""
        if not ObjectId.is_valid(user_id):
            return None

        doc = await self.collection.find_one({"_id": ObjectId(user_id)})
        if doc:
            return User(**doc)
        return None
    
    async def get_user_by_employee_id(self, employee_id: str) -> Optional[User]:
        """Get user by employee_id"""
        doc = await self.collection.find_one({"employee_id": employee_id})
        if doc:
            return User(**doc)
        return None
    
    async def get_user_by_id_or_employee_id(self, identifier: str) -> Optional[User]:
        """Get user by either MongoDB _id (ObjectId) or employee_id"""
        # Try as ObjectId first
        if ObjectId.is_valid(identifier):
            user = await self.get_user_by_id(identifier)
            if user:
                return user
        
        # Try as employee_id
        return await self.get_user_by_employee_id(identifier)

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
    
    async def get_all_users(self, skip: int = 0, limit: int = 100, search: Optional[str] = None, access_level: Optional[str] = None, status: Optional[str] = None) -> tuple[List[User], int]:
        """Get all users with pagination, search, and filtering (for admin)"""
        query = {}
        
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"employee_id": {"$regex": search, "$options": "i"}}
            ]
        
        if access_level:
            query["access_level"] = access_level
        
        if status:
            query["status"] = status
        
        # Get total count
        total = await self.collection.count_documents(query)
        
        # Get paginated results
        users = []
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("name", 1)
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            # Exclude face_encodings from list view for performance
            if "face_encodings" in doc:
                doc["face_encodings"] = []  # Don't send encoding data in list
            users.append(User(**doc))
        
        return users, total
    
    async def check_employee_id_exists(self, employee_id: str, exclude_user_id: Optional[str] = None) -> bool:
        """Check if employee_id already exists"""
        query = {"employee_id": employee_id}
        if exclude_user_id and ObjectId.is_valid(exclude_user_id):
            query["_id"] = {"$ne": ObjectId(exclude_user_id)}
        
        count = await self.collection.count_documents(query)
        return count > 0
    
    async def check_name_exists(self, name: str, exclude_user_id: Optional[str] = None) -> bool:
        """Check if name already exists (case-insensitive)"""
        query = {"name": {"$regex": f"^{name}$", "$options": "i"}}  # Case-insensitive exact match
        if exclude_user_id and ObjectId.is_valid(exclude_user_id):
            query["_id"] = {"$ne": ObjectId(exclude_user_id)}
        
        count = await self.collection.count_documents(query)
        return count > 0
    
    async def generate_unique_employee_id(self) -> str:
        """Generate a unique 4-digit employee ID"""
        import random
        
        max_attempts = 100  # Prevent infinite loop
        for _ in range(max_attempts):
            # Generate random 4-digit number (1000-9999)
            employee_id = str(random.randint(1000, 9999))
            
            # Check if it already exists
            if not await self.check_employee_id_exists(employee_id):
                return employee_id
        
        # If we couldn't generate unique ID (very unlikely), raise error
        raise Exception("Unable to generate unique employee ID after 100 attempts")
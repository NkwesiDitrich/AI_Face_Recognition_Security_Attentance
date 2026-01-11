"""
Admin Repository
Database operations for Admin entities
"""

from typing import Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.domains.admin.models import Admin
from bson import ObjectId


class AdminRepository:
    """Repository for admin database operations"""
    
    def __init__(self, database: AsyncIOMotorDatabase):
        self.collection = database.get_collection("admins")
    
    async def find_by_email(self, email: str) -> Optional[Admin]:
        """Find an admin by email"""
        doc = await self.collection.find_one({"email": email})
        if doc:
            # Convert MongoDB document to Admin model
            # Handle _id to id conversion
            admin_data = {
                "_id": str(doc["_id"]),
                "email": doc["email"],
                "name": doc["name"],
                "password_hash": doc["password_hash"],  # Ensure password_hash is preserved
                "role": doc.get("role", "admin"),
                "is_active": doc.get("is_active", True),
                "created_at": doc.get("created_at"),
                "last_login_at": doc.get("last_login_at")
            }
            return Admin(**admin_data)
        return None
    
    async def find_by_id(self, admin_id: str) -> Optional[Admin]:
        """Find an admin by ID"""
        try:
            doc = await self.collection.find_one({"_id": ObjectId(admin_id)})
            if doc:
                # Convert MongoDB document to Admin model
                admin_data = {
                    "_id": str(doc["_id"]),
                    "email": doc["email"],
                    "name": doc["name"],
                    "password_hash": doc["password_hash"],  # Ensure password_hash is preserved
                    "role": doc.get("role", "admin"),
                    "is_active": doc.get("is_active", True),
                    "created_at": doc.get("created_at"),
                    "last_login_at": doc.get("last_login_at")
                }
                return Admin(**admin_data)
        except:
            pass
        return None
    
    async def create(self, admin: Admin) -> Admin:
        """Create a new admin"""
        admin_dict = admin.model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(admin_dict)
        admin.id = str(result.inserted_id)
        return admin
    
    async def update_last_login(self, admin_id: str):
        """Update last login timestamp"""
        from datetime import datetime
        await self.collection.update_one(
            {"_id": ObjectId(admin_id)},
            {"$set": {"last_login_at": datetime.utcnow()}}
        )
    
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Admin]:
        """Get all admins (for super admin only)"""
        cursor = self.collection.find().skip(skip).limit(limit)
        admins = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            admins.append(Admin(**doc))
        return admins
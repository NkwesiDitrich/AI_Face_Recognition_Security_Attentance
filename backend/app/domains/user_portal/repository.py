from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.domains.user_portal.models import UserPortalCredential, UserPortalLog
from datetime import datetime, timezone
from bson import ObjectId

class UserPortalCredentialRepository:
    """Repository for user portal credentials"""
    
    def __init__(self, database: AsyncIOMotorDatabase):
        self.collection = database.get_collection("user_portal_credentials")
    
    async def get_by_user_id(self, user_id: str) -> Optional[UserPortalCredential]:
        """Get credentials by user ID"""
        doc = await self.collection.find_one({"user_id": user_id})
        if doc:
            doc["_id"] = str(doc["_id"])
            return UserPortalCredential(**doc)
        return None
    
    async def create_credential(self, credential: UserPortalCredential) -> UserPortalCredential:
        """Create new credentials"""
        credential_dict = credential.model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(credential_dict)
        credential.id = str(result.inserted_id)
        return credential
    
    async def update_password(self, user_id: str, password_hash: str) -> bool:
        """Update password hash"""
        result = await self.collection.update_one(
            {"user_id": user_id},
            {"$set": {"password_hash": password_hash}}
        )
        return result.modified_count > 0
    
    async def update_last_login(self, user_id: str) -> bool:
        """Update last login timestamp"""
        result = await self.collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_login": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0

class UserPortalLogRepository:
    """Repository for user portal logs"""
    
    def __init__(self, database: AsyncIOMotorDatabase):
        self.collection = database.get_collection("user_portal_logs")
    
    async def create_log(self, log: UserPortalLog) -> UserPortalLog:
        """Create a log entry"""
        log_dict = log.model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(log_dict)
        log.id = str(result.inserted_id)
        return log
    
    async def get_logs_by_user(
        self, 
        user_id: str, 
        limit: int = 50
    ) -> list[UserPortalLog]:
        """Get logs for a user"""
        cursor = self.collection.find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
        logs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            logs.append(UserPortalLog(**doc))
        return logs

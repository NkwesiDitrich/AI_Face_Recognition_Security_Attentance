from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.domains.system_log.models import SystemLog
from datetime import datetime

class SystemLogRepository:
    """Repository for system log database operations."""

    def __init__(self, database: AsyncIOMotorDatabase):
        self.collection = database.get_collection("system_logs")

    async def add_log(self, log: SystemLog) -> SystemLog:
        """Save system log to MongoDB."""
        try:
            log_dict = log.model_dump(by_alias=True, exclude={"id"})
            # Ensure timestamp is set
            if "timestamp" not in log_dict or log_dict["timestamp"] is None:
                log_dict["timestamp"] = datetime.utcnow()
            result = await self.collection.insert_one(log_dict)
            log.id = str(result.inserted_id)
            return log
        except Exception as e:
            print(f"❌ Error saving system log: {e}")
            raise

    async def get_logs_by_user(self, user_id: str) -> List[SystemLog]:
        """Get all logs for a user."""
        cursor = self.collection.find({"user_id": user_id}).sort("timestamp", -1)
        logs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            logs.append(SystemLog(**doc))
        return logs

    async def get_logs_by_session(self, session_id: str) -> List[SystemLog]:
        """Get all logs for a session."""
        cursor = self.collection.find({"session_id": session_id}).sort("timestamp", 1)
        logs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            logs.append(SystemLog(**doc))
        return logs

    async def get_logs_by_type(self, log_type: str, limit: int = 100) -> List[SystemLog]:
        """Get logs by type."""
        cursor = self.collection.find({"type": log_type}).sort("timestamp", -1).limit(limit)
        logs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            logs.append(SystemLog(**doc))
        return logs

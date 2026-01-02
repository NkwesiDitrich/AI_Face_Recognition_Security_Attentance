from typing import List
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.domains.attendance.models import AttendanceLog

class AttendanceRepository:
    """Repository for AttendanceLog database operations."""

    def __init__(self, database: AsyncIOMotorDatabase):
        self.collection = database.get_collection("attendance_logs")

    async def add_log(self, log: AttendanceLog) -> AttendanceLog:
        """Save attendance log to MongoDB."""
        try:
            log_dict = log.model_dump(by_alias=True, exclude={"id"})
            result = await self.collection.insert_one(log_dict)
            log.id = str(result.inserted_id)
            print(f"✅ Saved attendance log: {log.id}")
            return log
        except Exception as e:
            print(f"❌ Error saving attendance log: {e}")
            raise

    async def get_logs_by_user(self, user_id: str) -> List[AttendanceLog]:
        """Get all attendance logs for a user."""
        cursor = self.collection.find({"user_id": user_id})
        logs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            logs.append(AttendanceLog(**doc))
        return logs

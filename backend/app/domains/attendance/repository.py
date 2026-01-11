from typing import List, Optional
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
    
    async def get_all_logs(
        self, 
        skip: int = 0, 
        limit: int = 100,
        user_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: Optional[str] = None
    ) -> tuple[List[AttendanceLog], int]:
        """Get all attendance logs with filtering (for admin)"""
        from datetime import datetime
        from bson import ObjectId
        
        query = {}
        
        if user_id:
            query["user_id"] = user_id
        
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                query["timestamp"]["$gte"] = start_dt
            if end_date:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                query["timestamp"]["$lte"] = end_dt
        
        if status:
            query["liveness"] = status
        
        # Get total count
        total = await self.collection.count_documents(query)
        
        # Get paginated results
        logs = []
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("timestamp", -1)
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            logs.append(AttendanceLog(**doc))
        
        return logs, total
    
    async def get_log_by_id(self, log_id: str) -> Optional[AttendanceLog]:
        """Get a single attendance log by ID"""
        from bson import ObjectId
        
        if not ObjectId.is_valid(log_id):
            return None
        
        doc = await self.collection.find_one({"_id": ObjectId(log_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
            return AttendanceLog(**doc)
        return None
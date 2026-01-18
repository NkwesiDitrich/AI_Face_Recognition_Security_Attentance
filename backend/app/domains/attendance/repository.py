from typing import List, Optional
from datetime import datetime
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

    async def get_logs_by_user(
        self, 
        user_id: str, 
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AttendanceLog]:
        """Get all attendance logs for a user with optional date filtering."""
        from datetime import datetime, timezone
        
        # Build query
        query = {
            "user_id": user_id, 
            "liveness": {"$exists": True, "$ne": "pending"}
        }
        
        # Add date filtering if provided
        if start_date or end_date:
            query["timestamp"] = {}
            if start_date:
                # Ensure timezone-aware (copy to avoid modifying parameter)
                start_dt = start_date
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                query["timestamp"]["$gte"] = start_dt
            if end_date:
                # Ensure timezone-aware (copy to avoid modifying parameter)
                end_dt = end_date
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                # Add 23:59:59 to end_date to include the entire day
                if end_dt.hour == 0 and end_dt.minute == 0:
                    end_dt = end_dt.replace(hour=23, minute=59, second=59)
                query["timestamp"]["$lte"] = end_dt
        
        # Query with limit and sort by timestamp descending
        cursor = self.collection.find(query).sort("timestamp", -1).limit(limit)
        
        logs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            # Skip records without liveness field
            if "liveness" not in doc or not doc["liveness"]:
                continue
            try:
                logs.append(AttendanceLog(**doc))
            except Exception as e:
                # Skip records that fail validation (old format)
                print(f"⚠️ Skipping invalid attendance record {doc.get('_id')}: {e}")
                continue
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
        
        # Filter by liveness status (exclude "pending" and missing liveness old records)
        if status:
            query["liveness"] = status
        else:
            # Exclude records with "pending" liveness or missing liveness field (old records)
            query["liveness"] = {"$exists": True, "$ne": "pending"}
        
        # Get total count
        total = await self.collection.count_documents(query)
        
        # Get paginated results
        logs = []
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("timestamp", -1)
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            # Skip records without liveness field (old records)
            if "liveness" not in doc or not doc["liveness"]:
                continue
            try:
                logs.append(AttendanceLog(**doc))
            except Exception as e:
                # Skip records that fail validation (old format)
                print(f"⚠️ Skipping invalid attendance record {doc.get('_id')}: {e}")
                continue
        
        return logs, total
    
    async def get_log_by_id(self, log_id: str) -> Optional[AttendanceLog]:
        """Get a single attendance log by ID"""
        from bson import ObjectId
        
        if not ObjectId.is_valid(log_id):
            return None
        
        doc = await self.collection.find_one({"_id": ObjectId(log_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
            # Skip records without liveness field
            if "liveness" not in doc or not doc["liveness"]:
                return None
            try:
                return AttendanceLog(**doc)
            except Exception as e:
                # Skip records that fail validation (old format)
                print(f"⚠️ Invalid attendance record {log_id}: {e}")
                return None
        return None
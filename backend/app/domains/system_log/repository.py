from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.domains.system_log.models import SystemLog
from datetime import datetime

class SystemLogRepository:
    """
    Repository for system log database operations.
    Routes logs to separate collections based on log type for better organization:
    - enrollment_logs: Face enrollment events (started, completed, reset, failed)
    - recognition_logs: Face recognition attempts (started, success, failed)
    - liveness_logs: Liveness detection events (started, attempt, passed, failed)
    - attendance_logs: Final attendance records (only after successful recognition + liveness)
    - admin_action_logs: Admin actions (manual overrides, deletions, etc.)
    - system_logs: Other system-level logs
    """

    # Collection mapping based on log type
    COLLECTION_MAP = {
        "face_enrollment": "enrollment_logs",
        "attendance_recognition": "recognition_logs",
        "liveness": "liveness_logs",
        "attendance_record": "attendance_logs",
        "admin_action": "admin_action_logs",
    }

    def __init__(self, database: AsyncIOMotorDatabase):
        self.database = database
        # Pre-initialize all collections for easy access
        self.collections = {
            "enrollment_logs": database.get_collection("enrollment_logs"),
            "recognition_logs": database.get_collection("recognition_logs"),
            "liveness_logs": database.get_collection("liveness_logs"),
            "attendance_logs": database.get_collection("attendance_logs"),
            "admin_action_logs": database.get_collection("admin_action_logs"),
            "system_logs": database.get_collection("system_logs"),
        }

    def _get_collection(self, log_type: str):
        """
        Get the appropriate collection for a log type.
        
        Args:
            log_type: Type of log (face_enrollment, attendance_recognition, liveness, attendance_record, admin_action)
        
        Returns:
            Collection instance for the log type, or system_logs as default
        """
        collection_name = self.COLLECTION_MAP.get(log_type, "system_logs")
        return self.collections[collection_name]

    async def add_log(self, log: SystemLog) -> SystemLog:
        """
        Save system log to the appropriate collection based on log type.
        
        Args:
            log: SystemLog instance to save
        
        Returns:
            SystemLog with assigned _id
        """
        try:
            # Get the appropriate collection based on log type
            collection = self._get_collection(log.type)
            
            log_dict = log.model_dump(by_alias=True, exclude={"id"})
            # Ensure timestamp is set
            if "timestamp" not in log_dict or log_dict["timestamp"] is None:
                log_dict["timestamp"] = datetime.utcnow()
            
            result = await collection.insert_one(log_dict)
            log.id = str(result.inserted_id)
            
            # Debug output to verify collection routing
            collection_name = self.COLLECTION_MAP.get(log.type, "system_logs")
            print(f"✅ Log saved to '{collection_name}': type={log.type}, stage={log.stage}, id={log.id[:8]}...")
            
            return log
        except Exception as e:
            print(f"❌ Error saving system log to collection '{self.COLLECTION_MAP.get(log.type, 'system_logs')}': {e}")
            raise

    async def get_logs_by_user(self, user_id: str, log_type: Optional[str] = None) -> List[SystemLog]:
        """
        Get all logs for a user, optionally filtered by log type.
        
        Args:
            user_id: User ID to search for
            log_type: Optional log type filter
        
        Returns:
            List of SystemLog entries
        """
        logs = []
        
        # If log_type specified, search only that collection
        if log_type and log_type in self.COLLECTION_MAP:
            collection_name = self.COLLECTION_MAP[log_type]
            collection = self.collections[collection_name]
            cursor = collection.find({"user_id": user_id}).sort("timestamp", -1)
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                logs.append(SystemLog(**doc))
        else:
            # Search all collections
            for collection in self.collections.values():
                cursor = collection.find({"user_id": user_id}).sort("timestamp", -1)
                async for doc in cursor:
                    doc["_id"] = str(doc["_id"])
                    logs.append(SystemLog(**doc))
            
            # Sort all logs by timestamp
            logs.sort(key=lambda x: x.timestamp, reverse=True)
        
        return logs

    async def get_logs_by_session(self, session_id: str) -> List[SystemLog]:
        """
        Get all logs for a session across all relevant collections.
        
        Args:
            session_id: Session ID to search for
        
        Returns:
            List of SystemLog entries sorted by timestamp
        """
        logs = []
        
        # Search recognition_logs and liveness_logs (main session collections)
        relevant_collections = [
            "recognition_logs",
            "liveness_logs",
            "attendance_logs"
        ]
        
        for collection_name in relevant_collections:
            collection = self.collections[collection_name]
            cursor = collection.find({"session_id": session_id}).sort("timestamp", 1)
            async for doc in cursor:
                doc["_id"] = str(doc["_id"])
                logs.append(SystemLog(**doc))
        
        # Sort by timestamp
        logs.sort(key=lambda x: x.timestamp)
        return logs

    async def get_logs_by_type(self, log_type: str, limit: int = 100) -> List[SystemLog]:
        """
        Get logs by type from the appropriate collection.
        
        Args:
            log_type: Type of log (face_enrollment, attendance_recognition, etc.)
            limit: Maximum number of logs to return
        
        Returns:
            List of SystemLog entries
        """
        collection = self._get_collection(log_type)
        cursor = collection.find({"type": log_type}).sort("timestamp", -1).limit(limit)
        logs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            logs.append(SystemLog(**doc))
        return logs

    async def get_enrollment_logs(self, limit: int = 100) -> List[SystemLog]:
        """Get enrollment logs from enrollment_logs collection."""
        return await self.get_logs_by_type("face_enrollment", limit)

    async def get_recognition_logs(self, limit: int = 100) -> List[SystemLog]:
        """Get recognition logs from recognition_logs collection."""
        return await self.get_logs_by_type("attendance_recognition", limit)

    async def get_liveness_logs(self, limit: int = 100) -> List[SystemLog]:
        """Get liveness logs from liveness_logs collection."""
        return await self.get_logs_by_type("liveness", limit)

    async def get_attendance_logs(self, limit: int = 100) -> List[SystemLog]:
        """Get attendance logs from attendance_logs collection."""
        return await self.get_logs_by_type("attendance_record", limit)

    async def get_admin_action_logs(self, limit: int = 100) -> List[SystemLog]:
        """Get admin action logs from admin_action_logs collection."""
        return await self.get_logs_by_type("admin_action", limit)
    
    async def get_enrollment_logs_by_user(self, user_id: str, limit: int = 100) -> List[SystemLog]:
        """Get enrollment logs for a specific user."""
        collection = self.collections["enrollment_logs"]
        cursor = collection.find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
        logs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            logs.append(SystemLog(**doc))
        return logs
    
    async def get_recognition_logs_by_session(self, session_id: str, limit: int = 100) -> List[SystemLog]:
        """Get recognition logs for a specific session."""
        collection = self.collections["recognition_logs"]
        cursor = collection.find({"session_id": session_id}).sort("timestamp", -1).limit(limit)
        logs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            logs.append(SystemLog(**doc))
        return logs
    
    async def get_liveness_logs_by_session(self, session_id: str, limit: int = 100) -> List[SystemLog]:
        """Get liveness logs for a specific session."""
        collection = self.collections["liveness_logs"]
        cursor = collection.find({"session_id": session_id}).sort("timestamp", -1).limit(limit)
        logs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            logs.append(SystemLog(**doc))
        return logs
    
    async def get_admin_action_logs_by_admin(self, admin_id: str, limit: int = 100) -> List[SystemLog]:
        """Get admin action logs for a specific admin."""
        collection = self.collections["admin_action_logs"]
        cursor = collection.find({"admin_id": admin_id}).sort("timestamp", -1).limit(limit)
        logs = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            logs.append(SystemLog(**doc))
        return logs

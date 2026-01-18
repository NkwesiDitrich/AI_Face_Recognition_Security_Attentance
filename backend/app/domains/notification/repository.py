from typing import List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.domains.notification.models import Notification, Message, MessageDelivery
from datetime import datetime, timezone

class NotificationRepository:
    """Repository for Notification database operations"""
    
    def __init__(self, database: AsyncIOMotorDatabase):
        self.collection = database.get_collection("notifications")
    
    async def create_notification(self, notification: Notification) -> Notification:
        """Create a new notification"""
        notification_dict = notification.model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(notification_dict)
        notification.id = str(result.inserted_id)
        return notification
    
    async def get_notifications_by_admin(
        self, 
        admin_id: str, 
        limit: int = 50,
        unread_only: bool = False
    ) -> List[Notification]:
        """Get notifications for an admin"""
        query = {"admin_id": admin_id}
        if unread_only:
            query["is_read"] = False
        
        cursor = self.collection.find(query).sort("created_at", -1).limit(limit)
        notifications = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            notifications.append(Notification(**doc))
        return notifications
    
    async def get_unread_count(self, admin_id: str) -> int:
        """Get count of unread notifications for an admin"""
        return await self.collection.count_documents({
            "admin_id": admin_id,
            "is_read": False
        })
    
    async def mark_as_read(self, notification_id: str, admin_id: str) -> bool:
        """Mark a notification as read"""
        result = await self.collection.update_one(
            {"_id": notification_id, "admin_id": admin_id},
            {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0
    
    async def mark_all_as_read(self, admin_id: str) -> int:
        """Mark all notifications as read for an admin"""
        result = await self.collection.update_many(
            {"admin_id": admin_id, "is_read": False},
            {"$set": {"is_read": True, "read_at": datetime.now(timezone.utc)}}
        )
        return result.modified_count
    
    async def delete_notification(self, notification_id: str, admin_id: str) -> bool:
        """Delete a notification"""
        result = await self.collection.delete_one({
            "_id": notification_id,
            "admin_id": admin_id
        })
        return result.deleted_count > 0

class MessageRepository:
    """Repository for Message database operations"""
    
    def __init__(self, database: AsyncIOMotorDatabase):
        self.collection = database.get_collection("messages")
        self.delivery_collection = database.get_collection("message_deliveries")
    
    async def create_message(self, message: Message) -> Message:
        """Create a new message"""
        message_dict = message.model_dump(by_alias=True, exclude={"id"})
        result = await self.collection.insert_one(message_dict)
        message.id = str(result.inserted_id)
        return message
    
    async def get_messages_by_sender(
        self, 
        admin_id: str, 
        limit: int = 50
    ) -> List[Message]:
        """Get messages sent by an admin"""
        cursor = self.collection.find({"sender_admin_id": admin_id}).sort("created_at", -1).limit(limit)
        messages = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            messages.append(Message(**doc))
        return messages
    
    async def get_message_by_id(self, message_id: str) -> Optional[Message]:
        """Get a message by ID"""
        from bson import ObjectId
        if not ObjectId.is_valid(message_id):
            return None
        
        doc = await self.collection.find_one({"_id": ObjectId(message_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
            return Message(**doc)
        return None
    
    async def update_message_status(
        self, 
        message_id: str, 
        status: str,
        sent_at: Optional[datetime] = None
    ) -> bool:
        """Update message status"""
        update_data = {"status": status}
        if sent_at:
            update_data["sent_at"] = sent_at
        
        from bson import ObjectId
        result = await self.collection.update_one(
            {"_id": ObjectId(message_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0
    
    async def create_delivery(self, delivery: MessageDelivery) -> MessageDelivery:
        """Create a message delivery record"""
        delivery_dict = delivery.model_dump(by_alias=True, exclude={"id"})
        result = await self.delivery_collection.insert_one(delivery_dict)
        delivery.id = str(result.inserted_id)
        return delivery
    
    async def get_deliveries_by_message(self, message_id: str) -> List[MessageDelivery]:
        """Get all delivery records for a message"""
        cursor = self.delivery_collection.find({"message_id": message_id})
        deliveries = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            deliveries.append(MessageDelivery(**doc))
        return deliveries
    
    async def mark_delivery_as_delivered(
        self, 
        message_id: str, 
        user_id: str
    ) -> bool:
        """Mark a delivery as delivered"""
        result = await self.delivery_collection.update_one(
            {"message_id": message_id, "user_id": user_id},
            {"$set": {
                "delivered": True,
                "delivered_at": datetime.now(timezone.utc)
            }}
        )
        return result.modified_count > 0
    
    async def mark_delivery_as_read(
        self, 
        message_id: str, 
        user_id: str
    ) -> bool:
        """Mark a delivery as read"""
        result = await self.delivery_collection.update_one(
            {"message_id": message_id, "user_id": user_id},
            {"$set": {
                "read": True,
                "read_at": datetime.now(timezone.utc)
            }}
        )
        return result.modified_count > 0
    
    async def update_message_stats(self, message_id: str) -> bool:
        """Update message delivery and read counts"""
        from bson import ObjectId
        
        # Count deliveries
        total = await self.delivery_collection.count_documents({"message_id": message_id})
        delivered = await self.delivery_collection.count_documents({
            "message_id": message_id,
            "delivered": True
        })
        read = await self.delivery_collection.count_documents({
            "message_id": message_id,
            "read": True
        })
        
        # Update message
        result = await self.collection.update_one(
            {"_id": ObjectId(message_id)},
            {"$set": {
                "total_recipients": total,
                "delivered_count": delivered,
                "read_count": read
            }}
        )
        return result.modified_count > 0

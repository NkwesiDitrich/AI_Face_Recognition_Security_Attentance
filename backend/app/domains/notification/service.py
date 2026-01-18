from typing import List, Optional
from app.domains.notification.models import (
    Notification, 
    Message, 
    MessageDelivery,
    NotificationPriority,
    NotificationCategory,
    MessageType,
    MessageTarget
)
from app.domains.notification.repository import NotificationRepository, MessageRepository
from app.domains.user.repository import UserRepository
from datetime import datetime, timezone

class NotificationService:
    """Service for notification operations"""
    
    def __init__(
        self,
        notification_repo: NotificationRepository,
        user_repo: UserRepository
    ):
        self.notification_repo = notification_repo
        self.user_repo = user_repo
    
    async def create_notification(
        self,
        admin_id: str,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.INFO,
        category: NotificationCategory = NotificationCategory.ADMIN_ACTION,
        source: Optional[str] = None,
        source_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> Notification:
        """Create a notification"""
        notification = Notification(
            admin_id=admin_id,
            title=title,
            message=message,
            priority=priority,
            category=category,
            source=source or "system",
            source_id=source_id,
            metadata=metadata or {}
        )
        return await self.notification_repo.create_notification(notification)
    
    async def notify_system_error(
        self,
        admin_id: str,
        error_message: str,
        source: Optional[str] = None
    ):
        """Create a system error notification"""
        return await self.create_notification(
            admin_id=admin_id,
            title="System Error",
            message=error_message,
            priority=NotificationPriority.CRITICAL,
            category=NotificationCategory.SYSTEM_ERROR,
            source=source or "system"
        )
    
    async def notify_liveness_failure(
        self,
        admin_id: str,
        user_id: str,
        user_name: str,
        attempts: int
    ):
        """Create a liveness failure notification"""
        if attempts >= 3:  # Only notify after 3+ failures
            return await self.create_notification(
                admin_id=admin_id,
                title="Repeated Liveness Failures",
                message=f"User {user_name} has failed liveness check {attempts} times",
                priority=NotificationPriority.WARNING,
                category=NotificationCategory.LIVENESS_FAILURE,
                source="attendance_system",
                source_id=user_id,
                metadata={"attempts": attempts, "user_name": user_name}
            )
        return None
    
    async def notify_missed_attendance(
        self,
        admin_id: str,
        user_id: str,
        user_name: str,
        expected_time: str
    ):
        """Create a missed attendance notification"""
        return await self.create_notification(
            admin_id=admin_id,
            title="Missed Attendance",
            message=f"User {user_name} did not check in at expected time ({expected_time})",
            priority=NotificationPriority.WARNING,
            category=NotificationCategory.MISSED_ATTENDANCE,
            source="attendance_system",
            source_id=user_id,
            metadata={"user_name": user_name, "expected_time": expected_time}
        )
    
    async def notify_suspicious_behavior(
        self,
        admin_id: str,
        user_id: str,
        user_name: str,
        behavior_description: str
    ):
        """Create a suspicious behavior notification"""
        return await self.create_notification(
            admin_id=admin_id,
            title="Suspicious Behavior Detected",
            message=f"Suspicious activity detected for user {user_name}: {behavior_description}",
            priority=NotificationPriority.CRITICAL,
            category=NotificationCategory.SUSPICIOUS_BEHAVIOR,
            source="attendance_system",
            source_id=user_id,
            metadata={"user_name": user_name, "behavior": behavior_description}
        )
    
    async def get_notifications(
        self,
        admin_id: str,
        limit: int = 50,
        unread_only: bool = False
    ) -> List[Notification]:
        """Get notifications for an admin"""
        return await self.notification_repo.get_notifications_by_admin(
            admin_id, limit, unread_only
        )
    
    async def get_unread_count(self, admin_id: str) -> int:
        """Get unread notification count"""
        return await self.notification_repo.get_unread_count(admin_id)
    
    async def mark_as_read(self, notification_id: str, admin_id: str) -> bool:
        """Mark a notification as read"""
        return await self.notification_repo.mark_as_read(notification_id, admin_id)
    
    async def mark_all_as_read(self, admin_id: str) -> int:
        """Mark all notifications as read"""
        return await self.notification_repo.mark_all_as_read(admin_id)

class MessageService:
    """Service for message operations"""
    
    def __init__(
        self,
        message_repo: MessageRepository,
        user_repo: UserRepository,
        notification_repo: NotificationRepository
    ):
        self.message_repo = message_repo
        self.user_repo = user_repo
        self.notification_repo = notification_repo
    
    async def send_message(
        self,
        sender_admin_id: str,
        sender_name: str,
        title: str,
        content: str,
        message_type: MessageType,
        target_type: MessageTarget,
        target_ids: List[str],
        scheduled_at: Optional[datetime] = None
    ) -> Message:
        """Send a message to users"""
        # Create message
        message = Message(
            title=title,
            content=content,
            message_type=message_type,
            target_type=target_type,
            target_ids=target_ids,
            sender_admin_id=sender_admin_id,
            sender_name=sender_name,
            scheduled_at=scheduled_at,
            status="pending"
        )
        
        # Get recipient user IDs
        user_ids = await self._get_recipient_user_ids(target_type, target_ids)
        message.total_recipients = len(user_ids)
        
        # Save message
        message = await self.message_repo.create_message(message)
        
        # Create delivery records
        for user_id in user_ids:
            delivery = MessageDelivery(
                message_id=message.id,
                user_id=user_id
            )
            await self.message_repo.create_delivery(delivery)
        
        # Mark as sent immediately (in real app, would queue for mobile push)
        message.status = "sent"
        message.sent_at = datetime.now(timezone.utc)
        await self.message_repo.update_message_status(message.id, "sent", message.sent_at)
        
        return message
    
    async def _get_recipient_user_ids(
        self,
        target_type: MessageTarget,
        target_ids: List[str]
    ) -> List[str]:
        """Get list of user IDs based on target type"""
        if target_type == MessageTarget.ALL_USERS:
            # Get all active users
            users, _ = await self.user_repo.get_all_users(limit=10000, status="active")
            return [str(user.id) for user in users]
        elif target_type == MessageTarget.GROUP:
            # Get users by access_level (group)
            user_ids = []
            for group_name in target_ids:
                users, _ = await self.user_repo.get_all_users(limit=10000, access_level=group_name, status="active")
                user_ids.extend([str(user.id) for user in users])
            return user_ids
        elif target_type == MessageTarget.SINGLE_USER:
            # Return target_ids as-is (they are user_ids)
            return target_ids
        return []
    
    async def get_message_delivery_status(self, message_id: str) -> dict:
        """Get delivery status for a message"""
        message = await self.message_repo.get_message_by_id(message_id)
        if not message:
            return {}
        
        deliveries = await self.message_repo.get_deliveries_by_message(message_id)
        
        return {
            "message": message.model_dump(by_alias=True),
            "deliveries": [d.model_dump(by_alias=True) for d in deliveries],
            "stats": {
                "total": message.total_recipients,
                "delivered": message.delivered_count,
                "read": message.read_count,
                "delivery_rate": (message.delivered_count / message.total_recipients * 100) if message.total_recipients > 0 else 0,
                "read_rate": (message.read_count / message.total_recipients * 100) if message.total_recipients > 0 else 0
            }
        }
    
    async def get_messages_by_sender(self, admin_id: str, limit: int = 50) -> List[Message]:
        """Get messages sent by an admin"""
        return await self.message_repo.get_messages_by_sender(admin_id, limit)

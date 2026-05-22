"""
Notification Service - Push notifications and alerts for trading events.

Provides:
- Order execution notifications
- Price alerts
- System notifications
- In-app toast notifications
- WebSocket-based real-time notifications
"""

import logging
import asyncio
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from uuid import uuid4
from enum import Enum
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    """Types of notifications."""
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_REJECTED = "order_rejected"
    PRICE_ALERT = "price_alert"
    DEPOSIT_RECEIVED = "deposit_received"
    WITHDRAWAL_COMPLETED = "withdrawal_completed"
    SYSTEM = "system"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class NotificationPriority(str, Enum):
    """Notification priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Notification:
    """Notification data structure."""
    notification_id: str
    user_id: str
    type: NotificationType
    title: str
    message: str
    priority: NotificationPriority = NotificationPriority.MEDIUM
    data: Dict = field(default_factory=dict)
    read: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: Optional[str] = None
    
    def to_dict(self) -> dict:
        result = asdict(self)
        result['type'] = self.type.value
        result['priority'] = self.priority.value
        return result


@dataclass
class PriceAlert:
    """Price alert configuration."""
    alert_id: str
    user_id: str
    symbol: str
    condition: str  # 'above', 'below', 'change_pct'
    target_value: float
    current_price: float = 0
    triggered: bool = False
    notification_sent: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    triggered_at: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


class NotificationService:
    """
    Service for managing notifications and alerts.
    
    Features:
    - Create and manage notifications
    - Price alerts with automatic triggering
    - WebSocket broadcast for real-time updates
    - Notification persistence in database
    """
    
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        self.db = db
        self._notifications: Dict[str, List[Notification]] = {}  # user_id -> notifications
        self._price_alerts: Dict[str, List[PriceAlert]] = {}  # user_id -> alerts
        self._websocket_clients: Dict[str, Set] = {}  # user_id -> websocket connections
        
        if db:
            self.notifications_collection = db.notifications
            self.alerts_collection = db.price_alerts
        
        logger.info("[NOTIFICATIONS] Service initialized")
    
    async def create_notification(
        self,
        user_id: str,
        type: NotificationType,
        title: str,
        message: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        data: Dict = None
    ) -> Notification:
        """Create and store a new notification."""
        notification = Notification(
            notification_id=f"notif_{uuid4().hex[:12]}",
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            priority=priority,
            data=data or {}
        )
        
        # Store in memory
        if user_id not in self._notifications:
            self._notifications[user_id] = []
        self._notifications[user_id].append(notification)
        
        # Keep only last 100 notifications per user
        if len(self._notifications[user_id]) > 100:
            self._notifications[user_id] = self._notifications[user_id][-100:]
        
        # Store in database if available
        if self.db:
            await self.notifications_collection.insert_one(notification.to_dict())
        
        # Broadcast via WebSocket
        await self._broadcast_notification(user_id, notification)
        
        logger.info(f"[NOTIFICATIONS] Created: {type.value} for user {user_id[:8]}...")
        
        return notification
    
    async def notify_order_filled(
        self,
        user_id: str,
        order_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        exchange: str
    ) -> Notification:
        """Send notification for filled order."""
        side_text = "Acquisto" if side.lower() == "buy" else "Vendita"
        
        return await self.create_notification(
            user_id=user_id,
            type=NotificationType.ORDER_FILLED,
            title=f"Ordine Eseguito ✓",
            message=f"{side_text} di {quantity:.4f} {symbol.split('-')[0]} @ €{price:,.2f} completato",
            priority=NotificationPriority.HIGH,
            data={
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "exchange": exchange,
                "total": quantity * price
            }
        )
    
    async def notify_order_rejected(
        self,
        user_id: str,
        order_id: str,
        symbol: str,
        reason: str
    ) -> Notification:
        """Send notification for rejected order."""
        return await self.create_notification(
            user_id=user_id,
            type=NotificationType.ORDER_REJECTED,
            title=f"Ordine Rifiutato ✗",
            message=f"L'ordine per {symbol} è stato rifiutato: {reason}",
            priority=NotificationPriority.HIGH,
            data={
                "order_id": order_id,
                "symbol": symbol,
                "reason": reason
            }
        )
    
    async def create_price_alert(
        self,
        user_id: str,
        symbol: str,
        condition: str,
        target_value: float
    ) -> PriceAlert:
        """Create a new price alert."""
        alert = PriceAlert(
            alert_id=f"alert_{uuid4().hex[:12]}",
            user_id=user_id,
            symbol=symbol,
            condition=condition,
            target_value=target_value
        )
        
        # Store in memory
        if user_id not in self._price_alerts:
            self._price_alerts[user_id] = []
        self._price_alerts[user_id].append(alert)
        
        # Store in database if available
        if self.db:
            await self.alerts_collection.insert_one(alert.to_dict())
        
        logger.info(f"[NOTIFICATIONS] Price alert created: {symbol} {condition} {target_value}")
        
        return alert
    
    async def check_price_alerts(self, symbol: str, current_price: float):
        """Check and trigger price alerts for a symbol."""
        triggered_alerts = []
        
        for user_id, alerts in self._price_alerts.items():
            for alert in alerts:
                if alert.triggered or alert.symbol != symbol:
                    continue
                
                should_trigger = False
                
                if alert.condition == 'above' and current_price >= alert.target_value:
                    should_trigger = True
                elif alert.condition == 'below' and current_price <= alert.target_value:
                    should_trigger = True
                elif alert.condition == 'change_pct':
                    if alert.current_price > 0:
                        change_pct = abs((current_price - alert.current_price) / alert.current_price * 100)
                        if change_pct >= alert.target_value:
                            should_trigger = True
                
                if should_trigger:
                    alert.triggered = True
                    alert.triggered_at = datetime.now(timezone.utc).isoformat()
                    triggered_alerts.append((user_id, alert))
                    
                    # Send notification
                    condition_text = {
                        'above': 'ha superato',
                        'below': 'è sceso sotto',
                        'change_pct': 'è variato di'
                    }.get(alert.condition, '')
                    
                    await self.create_notification(
                        user_id=user_id,
                        type=NotificationType.PRICE_ALERT,
                        title=f"Alert Prezzo {symbol} 🔔",
                        message=f"{symbol} {condition_text} €{alert.target_value:,.2f}. Prezzo attuale: €{current_price:,.2f}",
                        priority=NotificationPriority.HIGH,
                        data={
                            "alert_id": alert.alert_id,
                            "symbol": symbol,
                            "condition": alert.condition,
                            "target_value": alert.target_value,
                            "current_price": current_price
                        }
                    )
        
        return triggered_alerts
    
    async def get_user_notifications(
        self,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50
    ) -> List[Dict]:
        """Get notifications for a user."""
        notifications = self._notifications.get(user_id, [])
        
        if unread_only:
            notifications = [n for n in notifications if not n.read]
        
        # Sort by creation time (newest first)
        notifications = sorted(notifications, key=lambda n: n.created_at, reverse=True)
        
        return [n.to_dict() for n in notifications[:limit]]
    
    async def get_user_alerts(self, user_id: str, active_only: bool = True) -> List[Dict]:
        """Get price alerts for a user."""
        alerts = self._price_alerts.get(user_id, [])
        
        if active_only:
            alerts = [a for a in alerts if not a.triggered]
        
        return [a.to_dict() for a in alerts]
    
    async def mark_notification_read(self, user_id: str, notification_id: str) -> bool:
        """Mark a notification as read."""
        notifications = self._notifications.get(user_id, [])
        
        for notification in notifications:
            if notification.notification_id == notification_id:
                notification.read = True
                
                if self.db:
                    await self.notifications_collection.update_one(
                        {"notification_id": notification_id},
                        {"$set": {"read": True}}
                    )
                
                return True
        
        return False
    
    async def mark_all_read(self, user_id: str) -> int:
        """Mark all notifications as read for a user."""
        count = 0
        notifications = self._notifications.get(user_id, [])
        
        for notification in notifications:
            if not notification.read:
                notification.read = True
                count += 1
        
        if self.db and count > 0:
            await self.notifications_collection.update_many(
                {"user_id": user_id, "read": False},
                {"$set": {"read": True}}
            )
        
        return count
    
    async def delete_alert(self, user_id: str, alert_id: str) -> bool:
        """Delete a price alert."""
        alerts = self._price_alerts.get(user_id, [])
        
        for i, alert in enumerate(alerts):
            if alert.alert_id == alert_id:
                alerts.pop(i)
                
                if self.db:
                    await self.alerts_collection.delete_one({"alert_id": alert_id})
                
                return True
        
        return False
    
    async def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications."""
        notifications = self._notifications.get(user_id, [])
        return sum(1 for n in notifications if not n.read)
    
    def register_websocket(self, user_id: str, websocket):
        """Register a WebSocket connection for a user."""
        if user_id not in self._websocket_clients:
            self._websocket_clients[user_id] = set()
        self._websocket_clients[user_id].add(websocket)
    
    def unregister_websocket(self, user_id: str, websocket):
        """Unregister a WebSocket connection."""
        if user_id in self._websocket_clients:
            self._websocket_clients[user_id].discard(websocket)
    
    async def _broadcast_notification(self, user_id: str, notification: Notification):
        """Broadcast notification to user's WebSocket connections."""
        if user_id not in self._websocket_clients:
            return
        
        message = {
            "type": "notification",
            "data": notification.to_dict()
        }
        
        dead_connections = []
        for ws in self._websocket_clients[user_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead_connections.append(ws)
        
        for ws in dead_connections:
            self._websocket_clients[user_id].discard(ws)


# Global instance
_notification_service: Optional[NotificationService] = None


def get_notification_service(db: Optional[AsyncIOMotorDatabase] = None) -> NotificationService:
    """Get or create the notification service instance."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService(db)
    return _notification_service


def set_notification_service(service: NotificationService):
    """Set the notification service instance."""
    global _notification_service
    _notification_service = service

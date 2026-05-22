"""
Transaction Audit Log Service.

Provides detailed audit logging for on/off-ramp transactions:
- Event tracking with timestamps
- Visual timeline generation
- Compliance-ready audit trail
"""

import logging
from typing import Optional, Dict, List
from datetime import datetime, timezone
from uuid import uuid4
from dataclasses import dataclass, field
from enum import Enum
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Types of audit events."""
    # Widget events
    WIDGET_OPENED = "widget_opened"
    WIDGET_CLOSED = "widget_closed"
    WIDGET_ERROR = "widget_error"
    
    # User actions
    MODE_SELECTED = "mode_selected"
    AMOUNT_ENTERED = "amount_entered"
    CURRENCY_SELECTED = "currency_selected"
    WALLET_ENTERED = "wallet_entered"
    
    # Order lifecycle
    ORDER_CREATED = "order_created"
    ORDER_LINKED = "order_linked"
    KYC_STARTED = "kyc_started"
    KYC_COMPLETED = "kyc_completed"
    KYC_FAILED = "kyc_failed"
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_FAILED = "payment_failed"
    
    # Transaction events
    CRYPTO_TRANSFER_INITIATED = "crypto_transfer_initiated"
    CRYPTO_TRANSFER_COMPLETED = "crypto_transfer_completed"
    FIAT_TRANSFER_INITIATED = "fiat_transfer_initiated"
    FIAT_TRANSFER_COMPLETED = "fiat_transfer_completed"
    
    # Completion
    ORDER_COMPLETED = "order_completed"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_FAILED = "order_failed"
    ORDER_REFUNDED = "order_refunded"
    
    # System events
    WEBHOOK_RECEIVED = "webhook_received"
    STATUS_UPDATE = "status_update"
    ERROR_OCCURRED = "error_occurred"


@dataclass
class AuditEvent:
    """A single audit event."""
    event_id: str
    session_id: str
    event_type: AuditEventType
    timestamp: str
    user_id: Optional[str] = None
    order_id: Optional[str] = None
    transak_order_id: Optional[str] = None
    description: str = ""
    metadata: Dict = field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "order_id": self.order_id,
            "transak_order_id": self.transak_order_id,
            "description": self.description,
            "metadata": self.metadata,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent
        }


@dataclass
class AuditSession:
    """An audit session grouping related events."""
    session_id: str
    user_id: Optional[str]
    order_id: Optional[str]
    product_type: str  # BUY or SELL
    status: str
    started_at: str
    ended_at: Optional[str] = None
    events: List[AuditEvent] = field(default_factory=list)
    summary: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "order_id": self.order_id,
            "product_type": self.product_type,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "events": [e.to_dict() for e in self.events],
            "event_count": len(self.events),
            "summary": self.summary
        }


class TransactionAuditService:
    """
    Service for detailed transaction audit logging.
    
    Features:
    - Real-time event tracking
    - Session-based grouping
    - Visual timeline generation
    - Compliance export
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.events_collection = db.audit_events
        self.sessions_collection = db.audit_sessions
        self._initialized = False
    
    async def initialize(self):
        """Initialize audit service."""
        if self._initialized:
            return
        
        # Create indexes
        await self.events_collection.create_index("event_id", unique=True)
        await self.events_collection.create_index("session_id")
        await self.events_collection.create_index("order_id")
        await self.events_collection.create_index("user_id")
        await self.events_collection.create_index("timestamp")
        await self.events_collection.create_index("event_type")
        
        await self.sessions_collection.create_index("session_id", unique=True)
        await self.sessions_collection.create_index("order_id")
        await self.sessions_collection.create_index("user_id")
        await self.sessions_collection.create_index("started_at")
        
        self._initialized = True
        logger.info("Transaction Audit Service initialized")
    
    async def create_session(
        self,
        user_id: Optional[str],
        product_type: str,
        order_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> AuditSession:
        """Create a new audit session."""
        now = datetime.now(timezone.utc)
        
        session = AuditSession(
            session_id=f"audit_{uuid4().hex[:12]}",
            user_id=user_id,
            order_id=order_id,
            product_type=product_type,
            status="active",
            started_at=now.isoformat(),
            summary=metadata or {}
        )
        
        await self.sessions_collection.insert_one(session.to_dict())
        
        # Log initial event
        await self.log_event(
            session_id=session.session_id,
            event_type=AuditEventType.WIDGET_OPENED,
            description=f"Widget opened for {product_type}",
            user_id=user_id,
            order_id=order_id,
            metadata={"product_type": product_type}
        )
        
        logger.info(f"[AUDIT] Session created: {session.session_id} | {product_type}")
        
        return session
    
    async def log_event(
        self,
        session_id: str,
        event_type: AuditEventType,
        description: str = "",
        user_id: Optional[str] = None,
        order_id: Optional[str] = None,
        transak_order_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> AuditEvent:
        """Log an audit event."""
        now = datetime.now(timezone.utc)
        
        event = AuditEvent(
            event_id=f"evt_{uuid4().hex[:12]}",
            session_id=session_id,
            event_type=event_type,
            timestamp=now.isoformat(),
            user_id=user_id,
            order_id=order_id,
            transak_order_id=transak_order_id,
            description=description,
            metadata=metadata or {},
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        await self.events_collection.insert_one(event.to_dict())
        
        # Update session with latest event
        update_data = {
            "last_event_type": event_type.value,
            "last_event_at": now.isoformat()
        }
        
        if order_id:
            update_data["order_id"] = order_id
        if transak_order_id:
            update_data["transak_order_id"] = transak_order_id
        
        await self.sessions_collection.update_one(
            {"session_id": session_id},
            {
                "$set": update_data,
                "$inc": {"event_count": 1}
            }
        )
        
        logger.debug(f"[AUDIT] Event logged: {event_type.value} | Session: {session_id}")
        
        return event
    
    async def close_session(
        self,
        session_id: str,
        status: str = "completed",
        summary: Optional[Dict] = None
    ):
        """Close an audit session."""
        now = datetime.now(timezone.utc)
        
        update_data = {
            "status": status,
            "ended_at": now.isoformat()
        }
        
        if summary:
            update_data["summary"] = summary
        
        await self.sessions_collection.update_one(
            {"session_id": session_id},
            {"$set": update_data}
        )
        
        # Log closing event
        await self.log_event(
            session_id=session_id,
            event_type=AuditEventType.WIDGET_CLOSED,
            description=f"Session closed with status: {status}",
            metadata={"final_status": status}
        )
        
        logger.info(f"[AUDIT] Session closed: {session_id} | Status: {status}")
    
    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session with all events."""
        session = await self.sessions_collection.find_one(
            {"session_id": session_id},
            {"_id": 0}
        )
        
        if session:
            # Get all events for this session
            events = await self.events_collection.find(
                {"session_id": session_id},
                {"_id": 0}
            ).sort("timestamp", 1).to_list(1000)
            
            session["events"] = events
        
        return session
    
    async def get_session_by_order(self, order_id: str) -> Optional[Dict]:
        """Get session by order ID."""
        session = await self.sessions_collection.find_one(
            {"order_id": order_id},
            {"_id": 0}
        )
        
        if session:
            events = await self.events_collection.find(
                {"session_id": session["session_id"]},
                {"_id": 0}
            ).sort("timestamp", 1).to_list(1000)
            
            session["events"] = events
        
        return session
    
    async def get_timeline(self, session_id: str) -> Dict:
        """Generate visual timeline data for a session."""
        session = await self.get_session(session_id)
        
        if not session:
            return {"error": "Session not found"}
        
        events = session.get("events", [])
        
        # Group events by phase
        phases = {
            "setup": [],
            "kyc": [],
            "payment": [],
            "transfer": [],
            "completion": []
        }
        
        phase_mapping = {
            AuditEventType.WIDGET_OPENED.value: "setup",
            AuditEventType.MODE_SELECTED.value: "setup",
            AuditEventType.AMOUNT_ENTERED.value: "setup",
            AuditEventType.CURRENCY_SELECTED.value: "setup",
            AuditEventType.WALLET_ENTERED.value: "setup",
            AuditEventType.ORDER_CREATED.value: "setup",
            AuditEventType.ORDER_LINKED.value: "setup",
            AuditEventType.KYC_STARTED.value: "kyc",
            AuditEventType.KYC_COMPLETED.value: "kyc",
            AuditEventType.KYC_FAILED.value: "kyc",
            AuditEventType.PAYMENT_INITIATED.value: "payment",
            AuditEventType.PAYMENT_RECEIVED.value: "payment",
            AuditEventType.PAYMENT_FAILED.value: "payment",
            AuditEventType.CRYPTO_TRANSFER_INITIATED.value: "transfer",
            AuditEventType.CRYPTO_TRANSFER_COMPLETED.value: "transfer",
            AuditEventType.FIAT_TRANSFER_INITIATED.value: "transfer",
            AuditEventType.FIAT_TRANSFER_COMPLETED.value: "transfer",
            AuditEventType.ORDER_COMPLETED.value: "completion",
            AuditEventType.ORDER_CANCELLED.value: "completion",
            AuditEventType.ORDER_FAILED.value: "completion",
            AuditEventType.ORDER_REFUNDED.value: "completion",
            AuditEventType.WIDGET_CLOSED.value: "completion"
        }
        
        for event in events:
            phase = phase_mapping.get(event["event_type"], "setup")
            phases[phase].append({
                "event_id": event["event_id"],
                "type": event["event_type"],
                "timestamp": event["timestamp"],
                "description": event["description"],
                "metadata": event.get("metadata", {})
            })
        
        # Calculate duration
        start_time = datetime.fromisoformat(session["started_at"].replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(session["ended_at"].replace("Z", "+00:00")) if session.get("ended_at") else datetime.now(timezone.utc)
        duration_seconds = (end_time - start_time).total_seconds()
        
        return {
            "session_id": session_id,
            "order_id": session.get("order_id"),
            "product_type": session.get("product_type"),
            "status": session.get("status"),
            "started_at": session.get("started_at"),
            "ended_at": session.get("ended_at"),
            "duration_seconds": duration_seconds,
            "duration_formatted": f"{int(duration_seconds // 60)}m {int(duration_seconds % 60)}s",
            "total_events": len(events),
            "phases": phases,
            "phase_summary": {
                phase: len(events) for phase, events in phases.items()
            }
        }
    
    async def get_user_sessions(
        self,
        user_id: str,
        limit: int = 20,
        skip: int = 0
    ) -> List[Dict]:
        """Get all sessions for a user."""
        cursor = self.sessions_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("started_at", -1).skip(skip).limit(limit)
        
        return await cursor.to_list(limit)
    
    async def export_session_report(self, session_id: str) -> Dict:
        """Export session as compliance report."""
        session = await self.get_session(session_id)
        
        if not session:
            return {"error": "Session not found"}
        
        timeline = await self.get_timeline(session_id)
        
        return {
            "report_type": "transaction_audit",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "session": {
                "id": session_id,
                "user_id": session.get("user_id"),
                "order_id": session.get("order_id"),
                "transak_order_id": session.get("transak_order_id"),
                "product_type": session.get("product_type"),
                "status": session.get("status"),
                "started_at": session.get("started_at"),
                "ended_at": session.get("ended_at")
            },
            "timeline": timeline,
            "events": session.get("events", []),
            "summary": session.get("summary", {})
        }


# Global instance
_audit_service: Optional[TransactionAuditService] = None


def get_audit_service() -> Optional[TransactionAuditService]:
    return _audit_service


def set_audit_service(service: TransactionAuditService):
    global _audit_service
    _audit_service = service

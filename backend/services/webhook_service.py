"""
Webhook Delivery Service for PoR Engine.

Provides real-time event broadcasting to registered webhook endpoints.

Features:
- Async webhook delivery with retry logic
- HMAC signature verification for security
- Event filtering and subscription management
- Delivery status tracking and logging
- Queue-based delivery for reliability
"""

import os
import logging
import asyncio
import hmac
import hashlib
import json
import aiohttp
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
from uuid import uuid4
from motor.motor_asyncio import AsyncIOMotorDatabase
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger("por.webhooks")


class WebhookEventType(str, Enum):
    """Webhook event types for transaction lifecycle."""
    # On-Ramp Events
    ONRAMP_QUOTE_CREATED = "onramp.quote.created"
    ONRAMP_QUOTE_ACCEPTED = "onramp.quote.accepted"
    ONRAMP_PAYMENT_PENDING = "onramp.payment.pending"
    ONRAMP_PAYMENT_DETECTED = "onramp.payment.detected"
    ONRAMP_PAYMENT_CONFIRMED = "onramp.payment.confirmed"
    ONRAMP_PAYMENT_FAILED = "onramp.payment.failed"
    ONRAMP_CRYPTO_SENDING = "onramp.crypto.sending"
    ONRAMP_CRYPTO_SENT = "onramp.crypto.sent"
    ONRAMP_CRYPTO_CONFIRMED = "onramp.crypto.confirmed"
    ONRAMP_COMPLETED = "onramp.completed"
    ONRAMP_FAILED = "onramp.failed"
    
    # Off-Ramp Events
    OFFRAMP_QUOTE_CREATED = "offramp.quote.created"
    OFFRAMP_QUOTE_ACCEPTED = "offramp.quote.accepted"
    OFFRAMP_DEPOSIT_PENDING = "offramp.deposit.pending"
    OFFRAMP_DEPOSIT_DETECTED = "offramp.deposit.detected"
    OFFRAMP_DEPOSIT_CONFIRMED = "offramp.deposit.confirmed"
    OFFRAMP_DEPOSIT_FAILED = "offramp.deposit.failed"
    OFFRAMP_SETTLEMENT_PENDING = "offramp.settlement.pending"
    OFFRAMP_SETTLEMENT_PROCESSING = "offramp.settlement.processing"
    OFFRAMP_SETTLEMENT_COMPLETED = "offramp.settlement.completed"
    OFFRAMP_PAYOUT_INITIATED = "offramp.payout.initiated"
    OFFRAMP_PAYOUT_COMPLETED = "offramp.payout.completed"
    OFFRAMP_COMPLETED = "offramp.completed"
    OFFRAMP_FAILED = "offramp.failed"
    
    # General Events
    QUOTE_EXPIRED = "quote.expired"
    QUOTE_CANCELLED = "quote.cancelled"
    
    # KYC / Compliance Events
    KYC_SUBMITTED = "kyc.submitted"
    KYC_APPROVED = "kyc.approved"
    KYC_REJECTED = "kyc.rejected"
    KYC_TIER_UPGRADED = "kyc.tier.upgraded"
    AML_ALERT_CREATED = "aml.alert.created"
    AML_ALERT_ESCALATED = "aml.alert.escalated"
    
    # Referral Events
    REFERRAL_CODE_APPLIED = "referral.code.applied"
    REFERRAL_BONUS_PAID = "referral.bonus.paid"
    
    # Trading Events
    TRADE_EXECUTED = "trade.executed"
    MARGIN_POSITION_OPENED = "margin.position.opened"
    MARGIN_POSITION_CLOSED = "margin.position.closed"
    MARGIN_LIQUIDATION = "margin.liquidation"
    
    # DCA Events
    DCA_PLAN_CREATED = "dca.plan.created"
    DCA_EXECUTION = "dca.execution"


class WebhookDeliveryStatus(str, Enum):
    """Webhook delivery status."""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class WebhookConfig:
    """Webhook configuration."""
    webhook_id: str
    url: str
    secret: str
    events: List[str]  # Event patterns like "onramp.*" or "offramp.completed"
    enabled: bool = True
    api_key_id: Optional[str] = None
    max_retries: int = 5
    retry_delays: List[int] = None  # Seconds between retries
    
    def __post_init__(self):
        if self.retry_delays is None:
            self.retry_delays = [30, 60, 300, 900, 3600]  # 30s, 1m, 5m, 15m, 1h


class WebhookService:
    """
    Enterprise-grade webhook delivery service.
    
    Handles real-time event broadcasting with:
    - HMAC signature verification
    - Automatic retry with exponential backoff
    - Event filtering
    - Delivery tracking
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.webhooks_collection = db.webhooks
        self.deliveries_collection = db.webhook_deliveries
        self._initialized = False
        self._delivery_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def initialize(self) -> bool:
        """Initialize webhook service."""
        if self._initialized:
            return True
        
        try:
            # Create indexes
            await self.webhooks_collection.create_index("webhook_id", unique=True)
            await self.webhooks_collection.create_index("api_key_id")
            await self.webhooks_collection.create_index("enabled")
            
            await self.deliveries_collection.create_index("delivery_id", unique=True)
            await self.deliveries_collection.create_index("webhook_id")
            await self.deliveries_collection.create_index("event_id")
            await self.deliveries_collection.create_index("status")
            await self.deliveries_collection.create_index("created_at")
            
            self._initialized = True
            logger.info("Webhook service initialized")
            
            # Start delivery worker
            await self.start_worker()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize webhook service: {e}")
            return False
    
    async def start_worker(self):
        """Start the background delivery worker."""
        if self._worker_task is None or self._worker_task.done():
            self._running = True
            self._worker_task = asyncio.create_task(self._delivery_worker())
            logger.info("Webhook delivery worker started")
    
    async def stop_worker(self):
        """Stop the background delivery worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            logger.info("Webhook delivery worker stopped")
    
    async def _delivery_worker(self):
        """Background worker for processing webhook deliveries."""
        while self._running:
            try:
                # Get next delivery from queue (with timeout)
                try:
                    delivery = await asyncio.wait_for(
                        self._delivery_queue.get(),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process delivery
                await self._process_delivery(delivery)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Webhook worker error: {e}")
                await asyncio.sleep(1)
    
    async def register_webhook(
        self,
        url: str,
        events: List[str],
        api_key_id: Optional[str] = None
    ) -> WebhookConfig:
        """Register a new webhook endpoint."""
        await self.initialize()
        
        webhook_id = f"whk_{uuid4().hex[:12]}"
        secret = f"whsec_{uuid4().hex}"
        
        config = WebhookConfig(
            webhook_id=webhook_id,
            url=url,
            secret=secret,
            events=events,
            enabled=True,
            api_key_id=api_key_id
        )
        
        doc = {
            "webhook_id": webhook_id,
            "url": url,
            "secret": secret,
            "events": events,
            "enabled": True,
            "api_key_id": api_key_id,
            "max_retries": config.max_retries,
            "retry_delays": config.retry_delays,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await self.webhooks_collection.insert_one(doc)
        logger.info(f"Webhook registered: {webhook_id} -> {url}")
        
        return config
    
    async def get_webhooks(
        self,
        api_key_id: Optional[str] = None,
        enabled_only: bool = True
    ) -> List[WebhookConfig]:
        """Get registered webhooks."""
        query = {}
        if api_key_id:
            query["api_key_id"] = api_key_id
        if enabled_only:
            query["enabled"] = True
        
        cursor = self.webhooks_collection.find(query)
        docs = await cursor.to_list(length=100)
        
        configs = []
        for doc in docs:
            configs.append(WebhookConfig(
                webhook_id=doc["webhook_id"],
                url=doc["url"],
                secret=doc["secret"],
                events=doc["events"],
                enabled=doc.get("enabled", True),
                api_key_id=doc.get("api_key_id"),
                max_retries=doc.get("max_retries", 5),
                retry_delays=doc.get("retry_delays", [30, 60, 300, 900, 3600])
            ))
        
        return configs
    
    async def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook."""
        result = await self.webhooks_collection.delete_one({"webhook_id": webhook_id})
        return result.deleted_count > 0
    
    def _match_event(self, event_type: str, patterns: List[str]) -> bool:
        """Check if event matches any of the subscription patterns."""
        for pattern in patterns:
            if pattern == "*":
                return True
            if pattern.endswith(".*"):
                prefix = pattern[:-2]
                if event_type.startswith(prefix):
                    return True
            if pattern == event_type:
                return True
        return False
    
    def _generate_signature(self, secret: str, timestamp: str, payload: str) -> str:
        """Generate HMAC-SHA256 signature for webhook."""
        message = f"{timestamp}.{payload}"
        signature = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def broadcast_event(
        self,
        event_type: WebhookEventType,
        quote_id: str,
        direction: str,
        state: str,
        data: Dict[str, Any],
        previous_state: Optional[str] = None
    ):
        """
        Broadcast an event to all matching webhooks.
        
        This is the main entry point for sending webhook events.
        """
        await self.initialize()
        
        event_id = f"evt_{uuid4().hex[:16]}"
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Build event payload
        payload = {
            "event_id": event_id,
            "event_type": event_type.value,
            "timestamp": timestamp,
            "api_version": "2.0.0",
            "data": {
                "quote_id": quote_id,
                "direction": direction,
                "state": state,
                **data
            },
            "previous_state": previous_state
        }
        
        # Get all enabled webhooks
        webhooks = await self.get_webhooks(enabled_only=True)
        
        # Queue deliveries for matching webhooks
        for webhook in webhooks:
            if self._match_event(event_type.value, webhook.events):
                delivery = {
                    "delivery_id": f"dlv_{uuid4().hex[:12]}",
                    "webhook_id": webhook.webhook_id,
                    "event_id": event_id,
                    "event_type": event_type.value,
                    "url": webhook.url,
                    "secret": webhook.secret,
                    "payload": payload,
                    "status": WebhookDeliveryStatus.PENDING.value,
                    "attempt": 0,
                    "max_retries": webhook.max_retries,
                    "retry_delays": webhook.retry_delays,
                    "created_at": timestamp
                }
                
                # Store delivery record
                await self.deliveries_collection.insert_one(delivery.copy())
                
                # Queue for delivery
                await self._delivery_queue.put(delivery)
                
                logger.info(f"Webhook queued: {event_type.value} -> {webhook.url}")
    
    async def _process_delivery(self, delivery: Dict):
        """Process a single webhook delivery."""
        delivery_id = delivery["delivery_id"]
        url = delivery["url"]
        secret = delivery["secret"]
        payload = delivery["payload"]
        attempt = delivery.get("attempt", 0) + 1
        max_retries = delivery.get("max_retries", 5)
        retry_delays = delivery.get("retry_delays", [30, 60, 300, 900, 3600])
        
        timestamp = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload)
        signature = self._generate_signature(secret, timestamp, payload_json)
        
        headers = {
            "Content-Type": "application/json",
            "X-NeoNoble-Signature": signature,
            "X-NeoNoble-Timestamp": timestamp,
            "X-NeoNoble-Event-ID": payload["event_id"],
            "X-NeoNoble-Event-Type": payload["event_type"]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=payload_json,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    status_code = response.status
                    response_body = await response.text()
                    
                    if 200 <= status_code < 300:
                        # Success
                        await self.deliveries_collection.update_one(
                            {"delivery_id": delivery_id},
                            {"$set": {
                                "status": WebhookDeliveryStatus.DELIVERED.value,
                                "delivered_at": datetime.now(timezone.utc).isoformat(),
                                "attempt": attempt,
                                "response_status": status_code,
                                "response_body": response_body[:1000]
                            }}
                        )
                        logger.info(f"Webhook delivered: {delivery_id} -> {url} ({status_code})")
                    else:
                        raise Exception(f"HTTP {status_code}: {response_body[:200]}")
                        
        except Exception as e:
            error_message = str(e)
            logger.warning(f"Webhook delivery failed: {delivery_id} -> {url} ({error_message})")
            
            if attempt < max_retries:
                # Schedule retry
                retry_delay = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
                
                await self.deliveries_collection.update_one(
                    {"delivery_id": delivery_id},
                    {"$set": {
                        "status": WebhookDeliveryStatus.RETRYING.value,
                        "attempt": attempt,
                        "last_error": error_message,
                        "next_retry_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                # Re-queue after delay
                asyncio.create_task(self._schedule_retry(delivery, retry_delay))
            else:
                # Max retries reached
                await self.deliveries_collection.update_one(
                    {"delivery_id": delivery_id},
                    {"$set": {
                        "status": WebhookDeliveryStatus.FAILED.value,
                        "attempt": attempt,
                        "last_error": error_message,
                        "failed_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                logger.error(f"Webhook permanently failed: {delivery_id} after {attempt} attempts")
    
    async def _schedule_retry(self, delivery: Dict, delay: int):
        """Schedule a retry after delay."""
        await asyncio.sleep(delay)
        delivery["attempt"] = delivery.get("attempt", 0) + 1
        await self._delivery_queue.put(delivery)
    
    async def get_delivery_status(self, delivery_id: str) -> Optional[Dict]:
        """Get delivery status."""
        doc = await self.deliveries_collection.find_one({"delivery_id": delivery_id})
        if doc:
            doc.pop("_id", None)
        return doc
    
    async def get_event_deliveries(self, event_id: str) -> List[Dict]:
        """Get all deliveries for an event."""
        cursor = self.deliveries_collection.find({"event_id": event_id})
        docs = await cursor.to_list(length=100)
        for doc in docs:
            doc.pop("_id", None)
        return docs
    
    async def get_recent_deliveries(
        self,
        status: Optional[WebhookDeliveryStatus] = None,
        limit: int = 50
    ) -> List[Dict]:
        """Get recent deliveries."""
        query = {}
        if status:
            query["status"] = status.value
        
        cursor = self.deliveries_collection.find(query).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        for doc in docs:
            doc.pop("_id", None)
        return docs


# State to event type mapping
STATE_TO_WEBHOOK_EVENT = {
    # On-Ramp mappings
    ("onramp", "QUOTE_CREATED"): WebhookEventType.ONRAMP_QUOTE_CREATED,
    ("onramp", "QUOTE_ACCEPTED"): WebhookEventType.ONRAMP_QUOTE_ACCEPTED,
    ("onramp", "PAYMENT_PENDING"): WebhookEventType.ONRAMP_PAYMENT_PENDING,
    ("onramp", "PAYMENT_DETECTED"): WebhookEventType.ONRAMP_PAYMENT_DETECTED,
    ("onramp", "PAYMENT_CONFIRMED"): WebhookEventType.ONRAMP_PAYMENT_CONFIRMED,
    ("onramp", "PAYMENT_FAILED"): WebhookEventType.ONRAMP_PAYMENT_FAILED,
    ("onramp", "CRYPTO_SENDING"): WebhookEventType.ONRAMP_CRYPTO_SENDING,
    ("onramp", "CRYPTO_SENT"): WebhookEventType.ONRAMP_CRYPTO_SENT,
    ("onramp", "CRYPTO_CONFIRMED"): WebhookEventType.ONRAMP_CRYPTO_CONFIRMED,
    ("onramp", "COMPLETED"): WebhookEventType.ONRAMP_COMPLETED,
    ("onramp", "FAILED"): WebhookEventType.ONRAMP_FAILED,
    
    # Off-Ramp mappings
    ("offramp", "QUOTE_CREATED"): WebhookEventType.OFFRAMP_QUOTE_CREATED,
    ("offramp", "QUOTE_ACCEPTED"): WebhookEventType.OFFRAMP_QUOTE_ACCEPTED,
    ("offramp", "DEPOSIT_PENDING"): WebhookEventType.OFFRAMP_DEPOSIT_PENDING,
    ("offramp", "DEPOSIT_DETECTED"): WebhookEventType.OFFRAMP_DEPOSIT_DETECTED,
    ("offramp", "DEPOSIT_CONFIRMED"): WebhookEventType.OFFRAMP_DEPOSIT_CONFIRMED,
    ("offramp", "DEPOSIT_FAILED"): WebhookEventType.OFFRAMP_DEPOSIT_FAILED,
    ("offramp", "SETTLEMENT_PENDING"): WebhookEventType.OFFRAMP_SETTLEMENT_PENDING,
    ("offramp", "SETTLEMENT_PROCESSING"): WebhookEventType.OFFRAMP_SETTLEMENT_PROCESSING,
    ("offramp", "SETTLEMENT_COMPLETED"): WebhookEventType.OFFRAMP_SETTLEMENT_COMPLETED,
    ("offramp", "PAYOUT_INITIATED"): WebhookEventType.OFFRAMP_PAYOUT_INITIATED,
    ("offramp", "PAYOUT_COMPLETED"): WebhookEventType.OFFRAMP_PAYOUT_COMPLETED,
    ("offramp", "COMPLETED"): WebhookEventType.OFFRAMP_COMPLETED,
    ("offramp", "FAILED"): WebhookEventType.OFFRAMP_FAILED,
    
    # General mappings
    ("*", "QUOTE_EXPIRED"): WebhookEventType.QUOTE_EXPIRED,
    ("*", "QUOTE_CANCELLED"): WebhookEventType.QUOTE_CANCELLED,
}


def get_webhook_event_type(direction: str, state: str) -> Optional[WebhookEventType]:
    """Get webhook event type for a state transition."""
    # Try direction-specific first
    event = STATE_TO_WEBHOOK_EVENT.get((direction, state))
    if event:
        return event
    # Try wildcard
    return STATE_TO_WEBHOOK_EVENT.get(("*", state))


# Global webhook service instance
webhook_service: Optional[WebhookService] = None


def get_webhook_service() -> Optional[WebhookService]:
    """Get the global webhook service instance."""
    return webhook_service


def set_webhook_service(service: WebhookService):
    """Set the global webhook service instance."""
    global webhook_service
    webhook_service = service

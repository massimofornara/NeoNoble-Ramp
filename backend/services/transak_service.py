"""
Transak Integration Service.

Provides on-ramp and off-ramp functionality via Transak widget:
- On-ramp: Fiat (EUR) → Crypto (USDT/USDC/BNB)
- Off-ramp: Crypto → Fiat (EUR)
- Webhook handling for order status
"""

import os
import logging
import aiohttp
import hmac
import hashlib
import time
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
from uuid import uuid4
from dataclasses import dataclass
from enum import Enum
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# Transak Configuration
TRANSAK_API_KEY = os.environ.get('TRANSAK_API_KEY', '')
TRANSAK_API_SECRET = os.environ.get('TRANSAK_API_SECRET', '')
TRANSAK_ENVIRONMENT = os.environ.get('TRANSAK_ENVIRONMENT', 'staging')

# API URLs
TRANSAK_STAGING_URL = 'https://global-stg.transak.com'
TRANSAK_PRODUCTION_URL = 'https://global.transak.com'

# Widget URLs
TRANSAK_WIDGET_STAGING = 'https://global-stg.transak.com'
TRANSAK_WIDGET_PRODUCTION = 'https://global.transak.com'


class TransakOrderStatus(str, Enum):
    """Transak order status."""
    PENDING = "PENDING"
    AWAITING_PAYMENT_FROM_USER = "AWAITING_PAYMENT_FROM_USER"
    PAYMENT_DONE_MARKED_BY_USER = "PAYMENT_DONE_MARKED_BY_USER"
    PROCESSING = "PROCESSING"
    PENDING_DELIVERY_FROM_TRANSAK = "PENDING_DELIVERY_FROM_TRANSAK"
    ON_HOLD_PENDING_DELIVERY_FROM_TRANSAK = "ON_HOLD_PENDING_DELIVERY_FROM_TRANSAK"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    EXPIRED = "EXPIRED"


class TransakProductType(str, Enum):
    """Transak product type."""
    BUY = "BUY"  # Fiat → Crypto
    SELL = "SELL"  # Crypto → Fiat


@dataclass
class TransakWidgetConfig:
    """Configuration for Transak widget."""
    api_key: str
    environment: str
    product_type: TransakProductType
    fiat_currency: str = "EUR"
    crypto_currency: str = "USDT"
    network: str = "bsc"
    wallet_address: Optional[str] = None
    email: Optional[str] = None
    fiat_amount: Optional[float] = None
    crypto_amount: Optional[float] = None
    disable_wallet_address_form: bool = False
    hide_exchange_screen: bool = False
    theme_color: str = "000000"
    redirect_url: Optional[str] = None
    
    def to_query_params(self) -> Dict[str, str]:
        """Convert to query parameters for widget URL."""
        params = {
            "apiKey": self.api_key,
            "environment": self.environment,
            "productsAvailed": self.product_type.value,
            "defaultFiatCurrency": self.fiat_currency,
            "defaultCryptoCurrency": self.crypto_currency,
            "network": self.network,
            "themeColor": self.theme_color,
        }
        
        if self.wallet_address:
            params["walletAddress"] = self.wallet_address
        if self.email:
            params["email"] = self.email
        if self.fiat_amount:
            params["defaultFiatAmount"] = str(self.fiat_amount)
        if self.crypto_amount:
            params["cryptoAmount"] = str(self.crypto_amount)
        if self.disable_wallet_address_form:
            params["disableWalletAddressForm"] = "true"
        if self.hide_exchange_screen:
            params["hideExchangeScreen"] = "true"
        if self.redirect_url:
            params["redirectURL"] = self.redirect_url
        
        return params


class TransakService:
    """
    Transak integration service for on/off-ramp.
    
    Features:
    - Widget URL generation
    - Order status tracking
    - Webhook verification
    - Full audit logging
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.orders_collection = db.transak_orders
        self.webhooks_collection = db.transak_webhooks
        
        self._initialized = False
        self._api_key = TRANSAK_API_KEY
        self._api_secret = TRANSAK_API_SECRET
        self._environment = TRANSAK_ENVIRONMENT
        
        # Set URLs based on environment
        if self._environment == 'production':
            self._api_url = TRANSAK_PRODUCTION_URL
            self._widget_url = TRANSAK_WIDGET_PRODUCTION
        else:
            self._api_url = TRANSAK_STAGING_URL
            self._widget_url = TRANSAK_WIDGET_STAGING
    
    async def initialize(self):
        """Initialize Transak service."""
        if self._initialized:
            return
        
        # Create indexes
        await self.orders_collection.create_index("order_id", unique=True)
        await self.orders_collection.create_index("transak_order_id")
        await self.orders_collection.create_index("user_id")
        await self.orders_collection.create_index("status")
        await self.orders_collection.create_index("created_at")
        await self.webhooks_collection.create_index("event_id", unique=True)
        await self.webhooks_collection.create_index("order_id")
        
        self._initialized = True
        
        if self._api_key:
            logger.info(
                f"Transak Service initialized:\n"
                f"  Environment: {self._environment}\n"
                f"  API Key: {self._api_key[:8]}..."
            )
        else:
            logger.warning("Transak Service initialized WITHOUT API KEY")
    
    def is_configured(self) -> bool:
        """Check if Transak is properly configured."""
        return bool(self._api_key)
    
    def generate_widget_url(
        self,
        product_type: TransakProductType,
        wallet_address: Optional[str] = None,
        email: Optional[str] = None,
        fiat_amount: Optional[float] = None,
        crypto_amount: Optional[float] = None,
        fiat_currency: str = "EUR",
        crypto_currency: str = "USDT",
        network: str = "bsc",
        redirect_url: Optional[str] = None
    ) -> str:
        """Generate Transak widget URL."""
        config = TransakWidgetConfig(
            api_key=self._api_key,
            environment=self._environment,
            product_type=product_type,
            fiat_currency=fiat_currency,
            crypto_currency=crypto_currency,
            network=network,
            wallet_address=wallet_address,
            email=email,
            fiat_amount=fiat_amount,
            crypto_amount=crypto_amount,
            redirect_url=redirect_url
        )
        
        params = config.to_query_params()
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        
        return f"{self._widget_url}?{query_string}"
    
    async def create_order_record(
        self,
        user_id: str,
        product_type: TransakProductType,
        fiat_currency: str,
        crypto_currency: str,
        fiat_amount: Optional[float] = None,
        crypto_amount: Optional[float] = None,
        wallet_address: Optional[str] = None,
        quote_id: Optional[str] = None
    ) -> Dict:
        """Create local order record before widget launch."""
        now = datetime.now(timezone.utc)
        
        order = {
            "order_id": f"transak_{uuid4().hex[:12]}",
            "user_id": user_id,
            "product_type": product_type.value,
            "status": "WIDGET_OPENED",
            "fiat_currency": fiat_currency,
            "fiat_amount": fiat_amount,
            "crypto_currency": crypto_currency,
            "crypto_amount": crypto_amount,
            "network": "bsc",
            "wallet_address": wallet_address,
            "transak_order_id": None,
            "quote_id": quote_id,
            "transaction_hash": None,
            "fees": {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }
        
        await self.orders_collection.insert_one(order)
        
        logger.info(f"[TRANSAK] Order record created: {order['order_id']} | {product_type.value}")
        
        return {k: v for k, v in order.items() if k != "_id"}
    
    async def link_transak_order(
        self,
        order_id: str,
        transak_order_id: str
    ) -> Optional[Dict]:
        """Link local order with Transak order ID."""
        now = datetime.now(timezone.utc)
        
        result = await self.orders_collection.find_one_and_update(
            {"order_id": order_id},
            {
                "$set": {
                    "transak_order_id": transak_order_id,
                    "status": TransakOrderStatus.PENDING.value,
                    "updated_at": now.isoformat()
                }
            },
            return_document=True
        )
        
        if result:
            logger.info(f"[TRANSAK] Order linked: {order_id} → {transak_order_id}")
            return {k: v for k, v in result.items() if k != "_id"}
        
        return None
    
    def verify_webhook_signature(
        self,
        payload: str,
        signature: str
    ) -> bool:
        """Verify Transak webhook signature."""
        if not self._api_secret:
            logger.warning("[TRANSAK] No API secret configured for webhook verification")
            return False
        
        expected_signature = hmac.new(
            self._api_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
    
    async def process_webhook(
        self,
        event_id: str,
        order_id: str,
        event_type: str,
        webhook_data: Dict
    ) -> Dict:
        """Process Transak webhook event."""
        now = datetime.now(timezone.utc)
        
        # Store webhook event
        webhook_record = {
            "event_id": event_id,
            "order_id": order_id,
            "event_type": event_type,
            "payload": webhook_data,
            "processed": False,
            "received_at": now.isoformat()
        }
        
        try:
            await self.webhooks_collection.insert_one(webhook_record)
        except Exception:
            # Duplicate event
            logger.warning(f"[TRANSAK] Duplicate webhook event: {event_id}")
            return {"status": "duplicate", "event_id": event_id}
        
        # Extract order data
        status = webhook_data.get("status", "").upper()
        transak_order_id = webhook_data.get("id") or order_id
        
        # Update order record
        update_data = {
            "status": status,
            "transak_order_id": transak_order_id,
            "updated_at": now.isoformat()
        }
        
        # Add transaction hash if available
        if webhook_data.get("transactionHash"):
            update_data["transaction_hash"] = webhook_data["transactionHash"]
        
        # Add amounts
        if webhook_data.get("fiatAmount"):
            update_data["fiat_amount"] = webhook_data["fiatAmount"]
        if webhook_data.get("cryptoAmount"):
            update_data["crypto_amount"] = webhook_data["cryptoAmount"]
        
        # Add fees
        if webhook_data.get("totalFeeInFiat"):
            update_data["fees.total_fiat"] = webhook_data["totalFeeInFiat"]
        if webhook_data.get("partnerFeeInLocalCurrency"):
            update_data["fees.partner_fee"] = webhook_data["partnerFeeInLocalCurrency"]
        
        # Mark completed timestamp
        if status == TransakOrderStatus.COMPLETED.value:
            update_data["completed_at"] = now.isoformat()
        
        # Update by transak_order_id or order_id
        result = await self.orders_collection.find_one_and_update(
            {"$or": [
                {"transak_order_id": transak_order_id},
                {"order_id": order_id}
            ]},
            {"$set": update_data},
            return_document=True
        )
        
        # Mark webhook as processed
        await self.webhooks_collection.update_one(
            {"event_id": event_id},
            {"$set": {"processed": True, "processed_at": now.isoformat()}}
        )
        
        logger.info(
            f"[TRANSAK] Webhook processed: {event_type} | Order: {transak_order_id} | Status: {status}"
        )
        
        return {
            "status": "processed",
            "event_id": event_id,
            "order_status": status,
            "order": {k: v for k, v in result.items() if k != "_id"} if result else None
        }
    
    async def get_order(self, order_id: str) -> Optional[Dict]:
        """Get order by ID."""
        order = await self.orders_collection.find_one(
            {"$or": [
                {"order_id": order_id},
                {"transak_order_id": order_id}
            ]}
        )
        
        if order:
            return {k: v for k, v in order.items() if k != "_id"}
        
        return None
    
    async def get_orders_by_user(
        self,
        user_id: str,
        limit: int = 20,
        skip: int = 0
    ) -> List[Dict]:
        """Get orders for a user."""
        cursor = self.orders_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("created_at", -1).skip(skip).limit(limit)
        
        return await cursor.to_list(limit)
    
    async def get_service_status(self) -> Dict:
        """Get Transak service status."""
        total_orders = await self.orders_collection.count_documents({})
        completed_orders = await self.orders_collection.count_documents(
            {"status": TransakOrderStatus.COMPLETED.value}
        )
        
        return {
            "configured": self.is_configured(),
            "environment": self._environment,
            "api_key_present": bool(self._api_key),
            "widget_url": self._widget_url,
            "total_orders": total_orders,
            "completed_orders": completed_orders
        }


# Global instance
_transak_service: Optional[TransakService] = None


def get_transak_service() -> Optional[TransakService]:
    return _transak_service


def set_transak_service(service: TransakService):
    global _transak_service
    _transak_service = service

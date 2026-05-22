"""
Webhook Management Routes.

Provides endpoints for managing webhook subscriptions and viewing delivery status.
"""

from fastapi import APIRouter, HTTPException, Request, Depends
from typing import List, Optional
from pydantic import BaseModel, Field
import logging

from services.webhook_service import (
    WebhookService,
    WebhookConfig,
    WebhookDeliveryStatus,
    get_webhook_service
)
from middleware.auth import HMACAuthMiddleware

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

# HMAC middleware for developer authentication
hmac_middleware: HMACAuthMiddleware = None


def set_hmac_middleware(middleware: HMACAuthMiddleware):
    global hmac_middleware
    hmac_middleware = middleware


# ========================
# Request/Response Models
# ========================

class WebhookRegisterRequest(BaseModel):
    """Request model for webhook registration."""
    url: str = Field(..., description="Webhook endpoint URL (HTTPS required for production)")
    events: List[str] = Field(
        default=["*"],
        description="Event patterns to subscribe to (e.g., 'onramp.*', 'offramp.completed')"
    )


class WebhookResponse(BaseModel):
    """Response model for webhook details."""
    webhook_id: str
    url: str
    events: List[str]
    enabled: bool
    secret: Optional[str] = None  # Only returned on creation


class DeliveryResponse(BaseModel):
    """Response model for delivery details."""
    delivery_id: str
    webhook_id: str
    event_id: str
    event_type: str
    status: str
    attempt: int
    created_at: str
    delivered_at: Optional[str] = None
    last_error: Optional[str] = None


# ========================
# Webhook Management Endpoints
# ========================

@router.post("/register", response_model=WebhookResponse)
async def register_webhook(request: WebhookRegisterRequest, http_request: Request):
    """
    Register a new webhook endpoint.
    
    **HMAC Authentication Required**
    
    Returns webhook configuration including the secret (only shown once).
    """
    auth_info = await hmac_middleware.authenticate(http_request)
    api_key_id = auth_info.get("api_key_id")
    
    webhook_svc = get_webhook_service()
    if not webhook_svc:
        raise HTTPException(status_code=503, detail="Webhook service not available")
    
    config = await webhook_svc.register_webhook(
        url=request.url,
        events=request.events,
        api_key_id=api_key_id
    )
    
    return WebhookResponse(
        webhook_id=config.webhook_id,
        url=config.url,
        events=config.events,
        enabled=config.enabled,
        secret=config.secret  # Only returned on creation
    )


@router.get("/list", response_model=List[WebhookResponse])
async def list_webhooks(http_request: Request):
    """
    List registered webhooks for the authenticated API key.
    
    **HMAC Authentication Required**
    """
    auth_info = await hmac_middleware.authenticate(http_request)
    api_key_id = auth_info.get("api_key_id")
    
    webhook_svc = get_webhook_service()
    if not webhook_svc:
        raise HTTPException(status_code=503, detail="Webhook service not available")
    
    configs = await webhook_svc.get_webhooks(api_key_id=api_key_id)
    
    return [
        WebhookResponse(
            webhook_id=c.webhook_id,
            url=c.url,
            events=c.events,
            enabled=c.enabled
        )
        for c in configs
    ]


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str, http_request: Request):
    """
    Delete a webhook subscription.
    
    **HMAC Authentication Required**
    """
    await hmac_middleware.authenticate(http_request)
    
    webhook_svc = get_webhook_service()
    if not webhook_svc:
        raise HTTPException(status_code=503, detail="Webhook service not available")
    
    success = await webhook_svc.delete_webhook(webhook_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    return {"message": "Webhook deleted", "webhook_id": webhook_id}


# ========================
# Delivery Status Endpoints
# ========================

@router.get("/deliveries/{delivery_id}", response_model=DeliveryResponse)
async def get_delivery_status(delivery_id: str, http_request: Request):
    """
    Get delivery status for a specific delivery.
    
    **HMAC Authentication Required**
    """
    await hmac_middleware.authenticate(http_request)
    
    webhook_svc = get_webhook_service()
    if not webhook_svc:
        raise HTTPException(status_code=503, detail="Webhook service not available")
    
    delivery = await webhook_svc.get_delivery_status(delivery_id)
    
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    
    return DeliveryResponse(
        delivery_id=delivery["delivery_id"],
        webhook_id=delivery["webhook_id"],
        event_id=delivery["event_id"],
        event_type=delivery["event_type"],
        status=delivery["status"],
        attempt=delivery.get("attempt", 0),
        created_at=delivery["created_at"],
        delivered_at=delivery.get("delivered_at"),
        last_error=delivery.get("last_error")
    )


@router.get("/deliveries/event/{event_id}", response_model=List[DeliveryResponse])
async def get_event_deliveries(event_id: str, http_request: Request):
    """
    Get all deliveries for a specific event.
    
    **HMAC Authentication Required**
    """
    await hmac_middleware.authenticate(http_request)
    
    webhook_svc = get_webhook_service()
    if not webhook_svc:
        raise HTTPException(status_code=503, detail="Webhook service not available")
    
    deliveries = await webhook_svc.get_event_deliveries(event_id)
    
    return [
        DeliveryResponse(
            delivery_id=d["delivery_id"],
            webhook_id=d["webhook_id"],
            event_id=d["event_id"],
            event_type=d["event_type"],
            status=d["status"],
            attempt=d.get("attempt", 0),
            created_at=d["created_at"],
            delivered_at=d.get("delivered_at"),
            last_error=d.get("last_error")
        )
        for d in deliveries
    ]


@router.get("/deliveries/recent")
async def get_recent_deliveries(
    status: Optional[str] = None,
    limit: int = 50,
    http_request: Request = None
):
    """
    Get recent webhook deliveries.
    
    **HMAC Authentication Required**
    """
    if http_request:
        await hmac_middleware.authenticate(http_request)
    
    webhook_svc = get_webhook_service()
    if not webhook_svc:
        raise HTTPException(status_code=503, detail="Webhook service not available")
    
    status_filter = WebhookDeliveryStatus(status) if status else None
    deliveries = await webhook_svc.get_recent_deliveries(status=status_filter, limit=limit)
    
    return {
        "count": len(deliveries),
        "deliveries": deliveries
    }


# ========================
# Webhook Testing Endpoint
# ========================

@router.post("/test")
async def test_webhook(request: WebhookRegisterRequest, http_request: Request):
    """
    Send a test event to a webhook URL.
    
    **HMAC Authentication Required**
    
    Sends a test.ping event to verify webhook connectivity.
    """
    await hmac_middleware.authenticate(http_request)
    
    webhook_svc = get_webhook_service()
    if not webhook_svc:
        raise HTTPException(status_code=503, detail="Webhook service not available")
    
    # Create a test webhook config
    from services.webhook_service import WebhookEventType
    from uuid import uuid4
    
    test_config = WebhookConfig(
        webhook_id=f"test_{uuid4().hex[:8]}",
        url=request.url,
        secret=f"test_secret_{uuid4().hex[:8]}",
        events=["*"],
        enabled=True
    )
    
    # Send test event
    import aiohttp
    import json
    import hmac
    import hashlib
    from datetime import datetime, timezone
    
    timestamp = datetime.now(timezone.utc).isoformat()
    payload = {
        "event_id": f"evt_test_{uuid4().hex[:8]}",
        "event_type": "test.ping",
        "timestamp": timestamp,
        "api_version": "2.0.0",
        "data": {
            "message": "This is a test webhook event",
            "test": True
        }
    }
    
    payload_json = json.dumps(payload)
    signature = hmac.new(
        test_config.secret.encode(),
        f"{timestamp}.{payload_json}".encode(),
        hashlib.sha256
    ).hexdigest()
    
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
                request.url,
                data=payload_json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                status_code = response.status
                response_body = await response.text()
                
                return {
                    "success": 200 <= status_code < 300,
                    "status_code": status_code,
                    "response_body": response_body[:500],
                    "test_secret": test_config.secret,
                    "headers_sent": headers
                }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "test_secret": test_config.secret
        }

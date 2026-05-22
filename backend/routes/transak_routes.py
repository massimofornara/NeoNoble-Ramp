"""
Transak Routes - On/Off-Ramp Widget Integration.

Provides endpoints for:
- Widget URL generation
- Order management
- Webhook handling
"""

from fastapi import APIRouter, HTTPException, Request, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone

from services.transak_service import (
    TransakService,
    TransakProductType,
    TransakOrderStatus,
    get_transak_service
)

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transak", tags=["Transak"])


# Request/Response Models

class WidgetUrlRequest(BaseModel):
    """Request to generate widget URL."""
    product_type: str = Field(..., description="BUY or SELL")
    fiat_currency: str = Field("EUR", description="Fiat currency")
    crypto_currency: str = Field("USDT", description="Crypto currency")
    network: str = Field("bsc", description="Network")
    wallet_address: Optional[str] = None
    email: Optional[str] = None
    fiat_amount: Optional[float] = None
    crypto_amount: Optional[float] = None
    redirect_url: Optional[str] = None


class OrderCreateRequest(BaseModel):
    """Request to create order record."""
    user_id: str
    product_type: str
    fiat_currency: str = "EUR"
    crypto_currency: str = "USDT"
    fiat_amount: Optional[float] = None
    crypto_amount: Optional[float] = None
    wallet_address: Optional[str] = None
    quote_id: Optional[str] = None


class OrderLinkRequest(BaseModel):
    """Request to link Transak order."""
    order_id: str
    transak_order_id: str


# Dependency

def get_service() -> TransakService:
    service = get_transak_service()
    if not service:
        raise HTTPException(status_code=503, detail="Transak service not available")
    return service


# Routes

@router.get("/status")
async def get_transak_status(service: TransakService = Depends(get_service)):
    """Get Transak service status."""
    return await service.get_service_status()


@router.post("/widget-url")
async def generate_widget_url(
    request: WidgetUrlRequest,
    service: TransakService = Depends(get_service)
):
    """Generate Transak widget URL."""
    if not service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Transak not configured. API key missing."
        )
    
    try:
        product_type = TransakProductType(request.product_type.upper())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product_type. Must be BUY or SELL"
        )
    
    widget_url = service.generate_widget_url(
        product_type=product_type,
        wallet_address=request.wallet_address,
        email=request.email,
        fiat_amount=request.fiat_amount,
        crypto_amount=request.crypto_amount,
        fiat_currency=request.fiat_currency,
        crypto_currency=request.crypto_currency,
        network=request.network,
        redirect_url=request.redirect_url
    )
    
    return {
        "widget_url": widget_url,
        "product_type": product_type.value,
        "environment": service._environment
    }


@router.post("/orders")
async def create_order(
    request: OrderCreateRequest,
    service: TransakService = Depends(get_service)
):
    """Create local order record before widget launch."""
    try:
        product_type = TransakProductType(request.product_type.upper())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid product_type. Must be BUY or SELL"
        )
    
    order = await service.create_order_record(
        user_id=request.user_id,
        product_type=product_type,
        fiat_currency=request.fiat_currency,
        crypto_currency=request.crypto_currency,
        fiat_amount=request.fiat_amount,
        crypto_amount=request.crypto_amount,
        wallet_address=request.wallet_address,
        quote_id=request.quote_id
    )
    
    return order


@router.post("/orders/link")
async def link_order(
    request: OrderLinkRequest,
    service: TransakService = Depends(get_service)
):
    """Link local order with Transak order ID."""
    order = await service.link_transak_order(
        order_id=request.order_id,
        transak_order_id=request.transak_order_id
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return order


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    service: TransakService = Depends(get_service)
):
    """Get order by ID."""
    order = await service.get_order(order_id)
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return order


@router.get("/orders")
async def get_user_orders(
    user_id: str = Query(...),
    limit: int = Query(20, le=100),
    skip: int = 0,
    service: TransakService = Depends(get_service)
):
    """Get orders for a user."""
    orders = await service.get_orders_by_user(
        user_id=user_id,
        limit=limit,
        skip=skip
    )
    
    return {"orders": orders, "count": len(orders)}


@router.post("/webhook")
async def handle_webhook(
    request: Request,
    service: TransakService = Depends(get_service)
):
    """Handle Transak webhook events."""
    try:
        # Get raw body for signature verification
        body = await request.body()
        signature = request.headers.get("X-Transak-Signature", "")
        
        # Verify signature if secret is configured
        if service._api_secret:
            if not service.verify_webhook_signature(body.decode(), signature):
                logger.warning("[TRANSAK] Invalid webhook signature")
                raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse webhook data
        webhook_data = await request.json()
        
        event_id = webhook_data.get("eventID", webhook_data.get("id", ""))
        order_id = webhook_data.get("orderId", webhook_data.get("id", ""))
        event_type = webhook_data.get("eventType", webhook_data.get("status", ""))
        
        if not event_id or not order_id:
            raise HTTPException(status_code=400, detail="Missing event or order ID")
        
        # Process webhook
        result = await service.process_webhook(
            event_id=event_id,
            order_id=order_id,
            event_type=event_type,
            webhook_data=webhook_data
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/currencies/fiat")
async def get_fiat_currencies():
    """Get supported fiat currencies."""
    return {
        "currencies": [
            {"code": "EUR", "name": "Euro", "symbol": "€", "supported": True},
            {"code": "USD", "name": "US Dollar", "symbol": "$", "supported": True},
            {"code": "GBP", "name": "British Pound", "symbol": "£", "supported": True}
        ]
    }


@router.get("/currencies/crypto")
async def get_crypto_currencies():
    """Get supported cryptocurrencies on BSC."""
    return {
        "currencies": [
            {"code": "USDT", "name": "Tether USD", "network": "bsc", "supported": True},
            {"code": "USDC", "name": "USD Coin", "network": "bsc", "supported": True},
            {"code": "BNB", "name": "Binance Coin", "network": "bsc", "supported": True},
            {"code": "NENO", "name": "NeoNoble Token", "network": "bsc", "supported": True}
        ]
    }

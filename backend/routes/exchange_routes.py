"""
Exchange Routes - Multi-Venue Trading API.

Provides endpoints for:
- Exchange connectivity management
- Order execution
- Balance queries
- Market data
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, timezone

from services.exchanges import (
    ConnectorManager,
    get_connector_manager,
    OrderSide,
    OrderType,
    OrderStatus
)

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exchanges", tags=["Exchanges"])


# Request/Response Models

class OrderRequest(BaseModel):
    """Request to place an order."""
    symbol: str = Field(..., description="Trading pair symbol (e.g., BNBEUR)")
    side: str = Field(..., description="buy or sell")
    quantity: float = Field(..., description="Order quantity")
    order_type: str = Field("market", description="market or limit")
    price: Optional[float] = Field(None, description="Limit price (required for limit orders)")
    venue: Optional[str] = Field(None, description="Specific venue (binance, kraken)")


class AdminEnableRequest(BaseModel):
    """Request to enable/disable trading."""
    enabled: bool
    user_id: Optional[str] = None
    reason: Optional[str] = None


# Dependency

def get_manager() -> ConnectorManager:
    manager = get_connector_manager()
    if not manager:
        raise HTTPException(status_code=503, detail="Exchange connectors not available")
    return manager


# Routes

@router.get("/status")
async def get_exchanges_status(manager: ConnectorManager = Depends(get_manager)):
    """Get exchange connector status."""
    return await manager.get_status()


@router.get("/ticker/{symbol}")
async def get_ticker(
    symbol: str,
    venue: Optional[str] = None,
    manager: ConnectorManager = Depends(get_manager)
):
    """
    Get ticker for a symbol.
    
    For NENO pairs (e.g., NENO-EUR, NENOEUR), returns data from 
    the virtual NENO exchange with fixed pricing.
    """
    # Use the manager's get_ticker which handles NENO automatically
    ticker = await manager.get_ticker(symbol, venue)
    
    if not ticker:
        raise HTTPException(status_code=404, detail=f"No ticker for {symbol}")
    
    # Determine venue name
    ticker_venue = venue if venue else ("neno_exchange" if "NENO" in symbol.upper() else "best")
    if not venue and "NENO" not in symbol.upper():
        _, ticker_venue = await manager.get_best_price(symbol)
    
    return {
        "venue": ticker_venue,
        "symbol": ticker.symbol,
        "bid": ticker.bid,
        "ask": ticker.ask,
        "last": ticker.last,
        "mid": ticker.mid,
        "spread_pct": ticker.spread_pct,
        "volume_24h": ticker.volume_24h,
        "timestamp": ticker.timestamp
    }


@router.get("/balances")
async def get_all_balances(manager: ConnectorManager = Depends(get_manager)):
    """Get balances from all connected venues."""
    balances = await manager.get_all_balances()
    
    return {
        "balances": {
            venue: [b.to_dict() for b in venue_balances]
            for venue, venue_balances in balances.items()
        }
    }


@router.get("/balance/{currency}")
async def get_aggregated_balance(
    currency: str,
    manager: ConnectorManager = Depends(get_manager)
):
    """Get aggregated balance for a currency."""
    return await manager.get_aggregated_balance(currency)


@router.post("/orders")
async def place_order(
    request: OrderRequest,
    manager: ConnectorManager = Depends(get_manager)
):
    """Place an order."""
    # Validate side
    try:
        side = OrderSide(request.side.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid side. Must be 'buy' or 'sell'")
    
    # Validate order type
    try:
        order_type = OrderType(request.order_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_type. Must be 'market' or 'limit'")
    
    # Execute order
    order, error = await manager.execute_order(
        symbol=request.symbol,
        side=side,
        quantity=request.quantity,
        order_type=order_type,
        price=request.price,
        venue=request.venue
    )
    
    if error and order.exchange == "shadow":
        # Shadow mode or disabled
        return {
            "warning": error,
            "order": order.to_dict(),
            "mode": "shadow"
        }
    
    return {
        "order": order.to_dict(),
        "mode": "live" if not manager.is_shadow_mode() else "shadow"
    }


@router.get("/orders")
async def get_orders(
    venue: Optional[str] = None,
    limit: int = Query(50, le=200),
    manager: ConnectorManager = Depends(get_manager)
):
    """Get order history."""
    # Get from database
    query = {}
    if venue:
        query["exchange"] = venue
    
    cursor = manager.orders_collection.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    orders = await cursor.to_list(limit)
    
    return {"orders": orders, "count": len(orders)}


# Admin Routes

@router.post("/admin/enable")
async def admin_enable_trading(
    request: AdminEnableRequest,
    manager: ConnectorManager = Depends(get_manager)
):
    """Enable or disable live trading (admin only)."""
    if request.enabled:
        await manager.enable_live_trading(request.user_id)
        return {"status": "enabled", "message": "Live trading enabled"}
    else:
        await manager.disable_live_trading(request.reason)
        return {"status": "disabled", "message": "Live trading disabled (shadow mode)"}


@router.get("/admin/config")
async def get_exchange_config(manager: ConnectorManager = Depends(get_manager)):
    """Get exchange configuration (admin only)."""
    config = await manager.config_collection.find_one({"config_type": "exchanges"}, {"_id": 0})
    return config or {}

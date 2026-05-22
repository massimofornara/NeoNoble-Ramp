"""
Developer Public API Routes.

Public API endpoints accessible with API keys:
- Market data
- Token information
- Trading data
- Rate limited per API key tier
"""

from fastapi import APIRouter, HTTPException, Header, Request
from typing import Optional
from datetime import datetime, timezone, timedelta
import hashlib

from database.mongodb import get_database

router = APIRouter(prefix="/public", tags=["Developer Public API"])

RATE_LIMITS = {"free": 100, "basic": 1000, "pro": 10000}


async def _validate_api_key(api_key: str) -> dict:
    """Validate API key and check rate limits."""
    db = get_database()
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    key_doc = await db.platform_api_keys.find_one({"key_hash": key_hash, "is_active": True})
    if not key_doc:
        key_doc = await db.platform_api_keys.find_one({"key_id": api_key, "is_active": True})
    if not key_doc:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=1)
    usage = await db.api_usage.count_documents({
        "key_id": str(key_doc.get("key_id", key_doc.get("_id"))),
        "timestamp": {"$gte": window_start}
    })
    limit = key_doc.get("rate_limit", RATE_LIMITS.get("free", 100))
    if usage >= limit:
        raise HTTPException(status_code=429, detail=f"Rate limit exceeded ({limit}/hour)")

    await db.api_usage.insert_one({
        "key_id": str(key_doc.get("key_id", key_doc.get("_id"))),
        "timestamp": now,
        "endpoint": "public_api"
    })
    await db.platform_api_keys.update_one(
        {"_id": key_doc["_id"]},
        {"$set": {"last_used": now}, "$inc": {"total_requests": 1}}
    )
    return key_doc


@router.get("/v1/market/coins")
async def public_market_data(
    vs_currency: str = "eur",
    limit: int = 32,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """Public API: Get market data for cryptocurrencies."""
    if x_api_key:
        await _validate_api_key(x_api_key)

    from routes.market_data_routes import get_market_data
    return await get_market_data(vs_currency=vs_currency, per_page=limit)


@router.get("/v1/market/ticker/{pair_id}")
async def public_ticker(
    pair_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """Public API: Get ticker for a trading pair."""
    if x_api_key:
        await _validate_api_key(x_api_key)

    from routes.trading_engine_routes import get_pair_ticker
    return await get_pair_ticker(pair_id)


@router.get("/v1/market/orderbook/{pair_id}")
async def public_orderbook(
    pair_id: str,
    depth: int = 20,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """Public API: Get order book for a trading pair."""
    if x_api_key:
        await _validate_api_key(x_api_key)

    from routes.trading_engine_routes import get_order_book
    return await get_order_book(pair_id, depth)


@router.get("/v1/market/candles/{pair_id}")
async def public_candles(
    pair_id: str,
    interval: str = "1h",
    limit: int = 100,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """Public API: Get OHLCV candle data."""
    if x_api_key:
        await _validate_api_key(x_api_key)

    from routes.trading_engine_routes import get_candles
    return await get_candles(pair_id, interval, limit)


@router.get("/v1/market/trades/{pair_id}")
async def public_recent_trades(
    pair_id: str,
    limit: int = 50,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """Public API: Get recent trades."""
    if x_api_key:
        await _validate_api_key(x_api_key)

    from routes.trading_engine_routes import get_recent_trades
    return await get_recent_trades(pair_id, limit)


@router.get("/v1/tokens")
async def public_tokens(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """Public API: Get platform tokens."""
    if x_api_key:
        await _validate_api_key(x_api_key)

    db = get_database()
    tokens = await db.tokens.find(
        {"status": {"$in": ["approved", "live"]}},
        {"_id": 0, "owner_id": 0}
    ).to_list(100)
    for t in tokens:
        if "created_at" in t and hasattr(t["created_at"], "isoformat"):
            t["created_at"] = t["created_at"].isoformat()
    return {"tokens": tokens, "total": len(tokens)}


@router.get("/v1/pairs")
async def public_trading_pairs(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """Public API: Get available trading pairs."""
    if x_api_key:
        await _validate_api_key(x_api_key)

    from routes.trading_engine_routes import get_trading_pairs
    return await get_trading_pairs()


@router.get("/v1/docs")
async def api_documentation():
    """Public API documentation."""
    return {
        "name": "NeoNoble Ramp Public API",
        "version": "1.0",
        "base_url": "/api/public/v1",
        "authentication": "Include X-API-Key header with your API key",
        "rate_limits": {"free": "100 req/hour", "basic": "1,000 req/hour", "pro": "10,000 req/hour"},
        "endpoints": [
            {"method": "GET", "path": "/v1/market/coins", "description": "Market data for 30+ cryptocurrencies", "params": ["vs_currency", "limit"]},
            {"method": "GET", "path": "/v1/market/ticker/{pair_id}", "description": "Ticker for a trading pair"},
            {"method": "GET", "path": "/v1/market/orderbook/{pair_id}", "description": "Order book levels", "params": ["depth"]},
            {"method": "GET", "path": "/v1/market/candles/{pair_id}", "description": "OHLCV candle data", "params": ["interval", "limit"]},
            {"method": "GET", "path": "/v1/market/trades/{pair_id}", "description": "Recent trades", "params": ["limit"]},
            {"method": "GET", "path": "/v1/tokens", "description": "Platform tokens"},
            {"method": "GET", "path": "/v1/pairs", "description": "Available trading pairs"},
        ]
    }

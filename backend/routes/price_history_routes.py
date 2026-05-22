"""
Price History Routes - API endpoints for NENO price history and charts.

Provides:
- OHLCV candlestick data
- Price statistics
- Multiple timeframes
"""

import logging
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

from services.neno_price_history import get_price_history_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/price-history", tags=["price-history"])


@router.get("/candles/{symbol}")
async def get_candles(
    symbol: str,
    timeframe: str = Query("1h", regex="^(1m|5m|15m|1h|4h|1d)$"),
    limit: int = Query(100, ge=1, le=1000),
    start_time: Optional[int] = None,
    end_time: Optional[int] = None
):
    """
    Get OHLCV candlestick data for a symbol.
    
    Args:
        symbol: Trading symbol (e.g., NENO-EUR)
        timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d)
        limit: Number of candles to return (max 1000)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
    
    Returns:
        List of OHLCV candles
    """
    # Only support NENO for now
    if 'NENO' not in symbol.upper():
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not supported")
    
    service = get_price_history_service()
    candles = service.get_candles(
        timeframe=timeframe,
        limit=limit,
        start_time=start_time,
        end_time=end_time
    )
    
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "count": len(candles),
        "candles": candles
    }


@router.get("/current/{symbol}")
async def get_current_price(symbol: str):
    """
    Get current price with 24h statistics.
    
    Args:
        symbol: Trading symbol (e.g., NENO-EUR)
    
    Returns:
        Current price and 24h stats
    """
    if 'NENO' not in symbol.upper():
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not supported")
    
    service = get_price_history_service()
    price_data = service.get_current_price()
    
    return {
        "symbol": symbol,
        **price_data
    }


@router.get("/stats/{symbol}")
async def get_price_statistics(symbol: str):
    """
    Get comprehensive price statistics.
    
    Args:
        symbol: Trading symbol (e.g., NENO-EUR)
    
    Returns:
        Price statistics including all-time high/low, market cap, etc.
    """
    if 'NENO' not in symbol.upper():
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not supported")
    
    service = get_price_history_service()
    stats = service.get_price_statistics()
    
    return {
        "symbol": symbol,
        **stats
    }


@router.get("/timeframes")
async def get_available_timeframes():
    """Get list of available timeframes."""
    return {
        "timeframes": [
            {"value": "1m", "label": "1 Minuto"},
            {"value": "5m", "label": "5 Minuti"},
            {"value": "15m", "label": "15 Minuti"},
            {"value": "1h", "label": "1 Ora"},
            {"value": "4h", "label": "4 Ore"},
            {"value": "1d", "label": "1 Giorno"}
        ]
    }

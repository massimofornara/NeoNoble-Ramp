from fastapi import APIRouter
from services.liquidity.public_orderbook_service import public_orderbook_service

router = APIRouter(prefix="/orderbook", tags=["OrderBook"])

@router.get("/{symbol}")
async def get_orderbook(symbol: str):
    return public_orderbook_service.get_snapshot(symbol.upper())

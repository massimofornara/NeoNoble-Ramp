"""
Hybrid Liquidity API Routes — NeoNoble Ramp.

Endpoints for the hybrid liquidity engine:
- Spread quotes
- Order placement / matching
- Execution priority
- Liquidity status
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from routes.auth import get_current_user
from services.hybrid_liquidity_engine import HybridLiquidityEngine

router = APIRouter(prefix="/hybrid", tags=["Hybrid Liquidity"])


class OrderRequest(BaseModel):
    side: str = Field(..., description="buy or sell")
    asset: str = Field(default="NENO")
    amount: float = Field(...)
    price_eur: float = Field(...)


@router.get("/status")
async def hybrid_status(current_user: dict = Depends(get_current_user)):
    """Hybrid liquidity engine status: order book, volume, spread config."""
    engine = HybridLiquidityEngine.get_instance()
    return await engine.get_status()


@router.get("/spread")
async def get_spread(
    asset: str = "NENO",
    side: str = "buy",
    amount: float = 1.0,
    current_user: dict = Depends(get_current_user),
):
    """Get dynamic spread quote for an asset."""
    engine = HybridLiquidityEngine.get_instance()
    user_id = current_user.get("user_id", "")

    from database.mongodb import get_database
    db = get_database()
    vol_agg = await db.neno_transactions.aggregate([
        {"$match": {"user_id": user_id, "status": "completed"}},
        {"$group": {"_id": None, "total": {"$sum": "$eur_value"}}},
    ]).to_list(1)
    user_volume = vol_agg[0]["total"] if vol_agg else 0

    return await engine.calculate_spread(asset, side, amount, user_volume)


@router.post("/order")
async def place_order(
    req: OrderRequest,
    current_user: dict = Depends(get_current_user),
):
    """Place order for internal matching."""
    engine = HybridLiquidityEngine.get_instance()
    return await engine.place_order(
        current_user.get("user_id", ""),
        req.side, req.asset, req.amount, req.price_eur,
    )


@router.post("/execute")
async def execute_with_priority(
    req: OrderRequest,
    current_user: dict = Depends(get_current_user),
):
    """Execute trade with priority: internal match -> market maker -> DEX."""
    engine = HybridLiquidityEngine.get_instance()
    return await engine.execute_with_priority(
        current_user.get("user_id", ""),
        req.side, req.asset, req.amount, req.price_eur,
    )

"""
Market Maker API Routes — NeoNoble Ramp.

Exposes Treasury, Pricing, PnL, and Inventory management endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from routes.auth import get_current_user

router = APIRouter(prefix="/market-maker", tags=["Market Maker"])


# ── Pricing ──

@router.get("/pricing")
async def get_mm_pricing():
    """Get live Market Maker pricing: bid, ask, spread, skew."""
    from services.market_maker_service import MarketMakerService
    mm = MarketMakerService.get_instance()
    return await mm.get_pricing()


# ── Treasury Inventory ──

@router.get("/treasury")
async def get_treasury(current_user: dict = Depends(get_current_user)):
    """Get full treasury inventory with available/locked breakdown."""
    from services.market_maker_service import MarketMakerService
    mm = MarketMakerService.get_instance()
    return await mm.get_treasury_inventory()


@router.get("/treasury/{asset}")
async def get_treasury_asset(asset: str, current_user: dict = Depends(get_current_user)):
    """Get treasury inventory for a specific asset."""
    from services.market_maker_service import MarketMakerService
    mm = MarketMakerService.get_instance()
    return await mm.get_asset_inventory(asset)


@router.post("/treasury/sync")
async def sync_treasury(current_user: dict = Depends(get_current_user)):
    """Force re-sync treasury balances from on-chain state."""
    if current_user.get("role", "").upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Solo admin")
    from services.market_maker_service import MarketMakerService
    mm = MarketMakerService.get_instance()
    return await mm.sync_onchain_balances()


# ── PnL ──

@router.get("/pnl")
async def get_pnl(hours: int = 24, current_user: dict = Depends(get_current_user)):
    """Get Market Maker PnL report: spread revenue, fee revenue, inventory changes."""
    from services.market_maker_service import MarketMakerService
    mm = MarketMakerService.get_instance()
    return await mm.get_pnl_report(hours)


# ── Order Book ──

@router.get("/order-book")
async def get_order_book(current_user: dict = Depends(get_current_user)):
    """Get current internal order book state."""
    from database.mongodb import get_database
    db = get_database()
    orders = await db.mm_order_book.find(
        {"status": "pending"}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {
        "orders": orders,
        "total_pending": len(orders),
    }


# ── Risk Dashboard ──

@router.get("/risk")
async def get_risk_dashboard(current_user: dict = Depends(get_current_user)):
    """Get Market Maker risk dashboard."""
    from services.market_maker_service import MarketMakerService, TREASURY_USER_EMAIL
    mm = MarketMakerService.get_instance()
    pricing = await mm.get_pricing()
    treasury = await mm.get_treasury_inventory()

    neno_inv = treasury["assets"].get("NENO", {})
    neno_amount = neno_inv.get("available_amount", 0)
    target = pricing.get("target_inventory", 500)

    risk_level = "low"
    if neno_amount < target * 0.2 or neno_amount > target * 3:
        risk_level = "high"
    elif neno_amount < target * 0.5 or neno_amount > target * 2:
        risk_level = "medium"

    return {
        "treasury_owner": TREASURY_USER_EMAIL,
        "risk_level": risk_level,
        "neno_inventory": round(neno_amount, 4),
        "target_inventory": target,
        "inventory_ratio": pricing.get("inventory_ratio", 0),
        "spread_bps": pricing.get("spread_bps", 0),
        "treasury_total_eur": treasury.get("total_value_eur", 0),
        "assets": treasury.get("assets", {}),
        "pricing": {
            "bid": pricing["bid"],
            "ask": pricing["ask"],
            "mid": pricing["mid_price"],
            "spread_pct": pricing["spread_pct"],
        },
    }

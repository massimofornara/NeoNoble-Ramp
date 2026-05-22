"""
Institutional Liquidity Router API Routes — NeoNoble Ramp.

Provides:
- Best execution routing quotes
- Routed order execution
- Router status and diagnostics
- Venue availability
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from routes.auth import get_current_user
from services.institutional_liquidity_router import InstitutionalLiquidityRouter

logger = logging.getLogger("router_routes")
router = APIRouter(prefix="/router", tags=["Institutional Liquidity Router"])


class RouteQuoteRequest(BaseModel):
    asset: str
    side: str  # buy | sell
    amount: float


class RouteExecuteRequest(BaseModel):
    asset: str
    side: str
    amount: float


@router.post("/quote")
async def get_route_quote(req: RouteQuoteRequest, current_user: dict = Depends(get_current_user)):
    """Get best execution route across all venues (no execution)."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    if req.side not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="Side must be buy or sell")

    lr = InstitutionalLiquidityRouter.get_instance()
    decision = await lr.find_best_route(req.asset, req.side, req.amount)

    return {
        "route_id": decision.route_id,
        "asset": decision.asset,
        "side": decision.side,
        "amount": decision.amount,
        "best_venue": decision.best_venue,
        "best_type": decision.best_type,
        "best_price": decision.best_price,
        "net_price": decision.net_price,
        "fee_eur": decision.fee_eur,
        "split": decision.split,
        "legs": decision.legs,
        "quotes": decision.all_quotes,
        "risk_checks": decision.risk_checks,
        "timestamp": decision.timestamp,
    }


@router.post("/execute")
async def execute_routed_order(req: RouteExecuteRequest, current_user: dict = Depends(get_current_user)):
    """Execute an order via the institutional liquidity router."""
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be > 0")
    if req.side not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="Side must be buy or sell")

    lr = InstitutionalLiquidityRouter.get_instance()
    result = await lr.execute_routed_order(req.asset, req.side, req.amount, current_user["user_id"])
    return result


@router.get("/status")
async def router_status(current_user: dict = Depends(get_current_user)):
    """Get institutional liquidity router status and venue availability."""
    lr = InstitutionalLiquidityRouter.get_instance()
    return await lr.get_status()


@router.get("/venues")
async def list_venues(current_user: dict = Depends(get_current_user)):
    """List all available liquidity venues with real-time connectivity status."""
    from services.exchanges.connector_manager import get_connector_manager
    cm = get_connector_manager()
    if not cm:
        return {"venues": {}, "error": "ConnectorManager not initialized"}

    status = await cm.get_status()
    return {
        "venues": status.get("venues", {}),
        "primary": status.get("primary_venue"),
        "fallback": status.get("fallback_venue"),
        "live_trading": status.get("enabled") and not status.get("shadow_mode"),
    }


@router.get("/fallback-matrix")
async def fallback_matrix(current_user: dict = Depends(get_current_user)):
    """Return the custom token fallback routing matrix."""
    from services.institutional_liquidity_router import STANDARD_PAIRS, INTERMEDIATE_TOKENS

    return {
        "standard_pairs": {k: v for k, v in STANDARD_PAIRS.items()},
        "custom_token_strategy": [
            {"priority": 1, "method": "direct_cex_listing", "description": "Check MEXC/Binance/Kraken for direct listing"},
            {"priority": 2, "method": "dex_direct_swap", "description": "PancakeSwap V2 direct swap"},
            {"priority": 3, "method": "intermediate_routing", "description": f"Route via {INTERMEDIATE_TOKENS}"},
            {"priority": 4, "method": "internal_rfq", "description": "Internal market maker / treasury inventory"},
        ],
        "intermediate_tokens": INTERMEDIATE_TOKENS,
        "split_threshold_eur": 5000,
    }

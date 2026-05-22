"""
Growth & Analytics Routes — NeoNoble Ramp.

Funnel metrics, retention, ARPU, incentives, cashback management.
"""

from fastapi import APIRouter, HTTPException, Depends

from routes.auth import get_current_user
from services.growth_analytics_engine import GrowthAnalyticsEngine
from services.monetization_engine import MonetizationEngine
from services.incentive_engine import IncentiveEngine

router = APIRouter(prefix="/growth", tags=["Growth Engine"])


@router.get("/dashboard")
async def growth_dashboard(current_user: dict = Depends(get_current_user)):
    """Complete growth dashboard (admin)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    engine = GrowthAnalyticsEngine.get_instance()
    return await engine.get_growth_dashboard()


@router.get("/funnel")
async def funnel_metrics(current_user: dict = Depends(get_current_user)):
    """Funnel conversion metrics (admin)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    engine = GrowthAnalyticsEngine.get_instance()
    return await engine.get_funnel_metrics()


@router.get("/retention")
async def retention_metrics(current_user: dict = Depends(get_current_user)):
    """Retention metrics (admin)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    engine = GrowthAnalyticsEngine.get_instance()
    return await engine.get_retention_metrics()


@router.get("/revenue")
async def revenue_breakdown(days: int = 30, current_user: dict = Depends(get_current_user)):
    """Revenue breakdown by source (admin)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    engine = MonetizationEngine.get_instance()
    return await engine.get_revenue_breakdown(days)


@router.get("/revenue/daily")
async def daily_revenue(days: int = 7, current_user: dict = Depends(get_current_user)):
    """Daily revenue for chart (admin)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    engine = MonetizationEngine.get_instance()
    return await engine.get_daily_revenue(days)


@router.get("/arpu")
async def arpu_metrics(current_user: dict = Depends(get_current_user)):
    """ARPU and LTV metrics (admin)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    engine = GrowthAnalyticsEngine.get_instance()
    return await engine.get_revenue_per_user()


# ── User-facing incentive endpoints ──

@router.get("/my-rewards")
async def my_rewards(current_user: dict = Depends(get_current_user)):
    """Get current user's rewards summary."""
    engine = IncentiveEngine.get_instance()
    return await engine.get_user_rewards(current_user["user_id"])


@router.get("/my-tier")
async def my_tier(current_user: dict = Depends(get_current_user)):
    """Get current user's cashback tier."""
    engine = IncentiveEngine.get_instance()
    return await engine.get_user_tier(current_user["user_id"])


@router.post("/claim-topup-bonus")
async def claim_topup_bonus(current_user: dict = Depends(get_current_user)):
    """Claim first top-up bonus."""
    engine = IncentiveEngine.get_instance()
    result = await engine.check_first_topup_bonus(current_user["user_id"])
    if not result.get("eligible"):
        raise HTTPException(status_code=400, detail="Bonus già reclamato")
    return result

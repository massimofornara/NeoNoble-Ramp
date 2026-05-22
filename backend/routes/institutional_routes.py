"""
Institutional API — LP, Capital Markets, Arbitrage, Compliance.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from routes.auth import get_current_user
from services.liquidity_provider_engine import LiquidityProvider
from services.capital_markets_engine import CapitalMarketsEngine
from services.arbitrage_engine import ArbitrageEngine
from services.compliance_engine import ComplianceEngine
from services.profit_engine import ProfitEngine
from services.risk_engine import RiskEngine

router = APIRouter(prefix="/institutional", tags=["Institutional"])


# ── Liquidity Providers ──

class RegisterLPRequest(BaseModel):
    name: str
    tier: str = Field(default="tier_1")
    type: str = Field(default="market_maker")
    supported_pairs: list = Field(default=["NENO/EUR"])
    min_order_eur: float = Field(default=1000)
    max_order_eur: float = Field(default=5000000)
    fee_bps: float = Field(default=5)


@router.post("/lp/register")
async def register_lp(req: RegisterLPRequest, current_user: dict = Depends(get_current_user)):
    lp = LiquidityProvider.get_instance()
    result = await lp.register_provider(req.name, req.tier, req.model_dump())
    result.pop("created_at", None)
    return result


@router.get("/lp/providers")
async def get_lp_providers(tier: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    lp = LiquidityProvider.get_instance()
    providers = await lp.get_providers(tier)
    for p in providers:
        p.pop("created_at", None)
    return {"providers": providers}


@router.get("/lp/quotes/{pair}")
async def get_lp_quotes(pair: str, side: str = "buy", amount: float = 1.0, current_user: dict = Depends(get_current_user)):
    lp = LiquidityProvider.get_instance()
    quotes = await lp.request_quote(pair, side, amount)
    return {"quotes": quotes}


@router.post("/lp/hedge")
async def hedge_position(asset: str = "NENO", amount: float = 1.0, direction: str = "sell",
                          current_user: dict = Depends(get_current_user)):
    lp = LiquidityProvider.get_instance()
    result = await lp.hedge_position(asset, amount, direction)
    result.pop("created_at", None)
    return result


@router.get("/lp/rebalance")
async def rebalance_check(current_user: dict = Depends(get_current_user)):
    lp = LiquidityProvider.get_instance()
    return await lp.rebalance_inventory()


# ── Capital Markets ──

@router.get("/structure")
async def corporate_structure(current_user: dict = Depends(get_current_user)):
    cm = CapitalMarketsEngine.get_instance()
    return await cm.get_corporate_structure()


@router.get("/financials")
async def financials(current_user: dict = Depends(get_current_user)):
    cm = CapitalMarketsEngine.get_instance()
    return await cm.get_financials()


@router.get("/investor-deck")
async def investor_deck(current_user: dict = Depends(get_current_user)):
    cm = CapitalMarketsEngine.get_instance()
    return await cm.get_investor_deck()


@router.get("/banking-rails")
async def banking_rails(current_user: dict = Depends(get_current_user)):
    cm = CapitalMarketsEngine.get_instance()
    return await cm.get_banking_rails()


# ── Arbitrage ──

@router.get("/arbitrage/scan")
async def scan_arbitrage(current_user: dict = Depends(get_current_user)):
    arb = ArbitrageEngine.get_instance()
    opps = await arb.scan_opportunities()
    return {"opportunities": opps, "count": len(opps)}


@router.get("/arbitrage/history")
async def arbitrage_history(limit: int = 50, current_user: dict = Depends(get_current_user)):
    arb = ArbitrageEngine.get_instance()
    return {"history": await arb.get_history(limit)}


@router.get("/arbitrage/stats")
async def arbitrage_stats(current_user: dict = Depends(get_current_user)):
    arb = ArbitrageEngine.get_instance()
    return await arb.get_stats()


# ── Compliance ──

@router.get("/compliance/safeguarding")
async def safeguarding(current_user: dict = Depends(get_current_user)):
    comp = ComplianceEngine.get_instance()
    return await comp.get_safeguarding_report()


@router.get("/compliance/regulatory-report")
async def regulatory_report(report_type: str = "emi", current_user: dict = Depends(get_current_user)):
    comp = ComplianceEngine.get_instance()
    return await comp.generate_regulatory_report(report_type)


@router.get("/compliance/audit-trail")
async def audit_trail(user_id: Optional[str] = None, limit: int = 100,
                      current_user: dict = Depends(get_current_user)):
    comp = ComplianceEngine.get_instance()
    return {"trail": await comp.get_audit_trail(user_id, limit)}


# ── PnL & Revenue ──

@router.get("/pnl")
async def get_pnl(period_hours: int = 24, current_user: dict = Depends(get_current_user)):
    profit = ProfitEngine.get_instance()
    return await profit.get_pnl(period_hours)


@router.get("/revenue/breakdown")
async def revenue_breakdown(days: int = 30, current_user: dict = Depends(get_current_user)):
    profit = ProfitEngine.get_instance()
    data = await profit.get_revenue_breakdown(days)
    for d in data:
        d["date"] = d.get("_id", {}).get("date")
        d["type"] = d.get("_id", {}).get("type")
        d.pop("_id", None)
    return {"breakdown": data}


# ── Risk ──

@router.get("/risk/treasury-check/{asset}")
async def treasury_check(asset: str, amount: float = 1.0, current_user: dict = Depends(get_current_user)):
    risk = RiskEngine.get_instance()
    return await risk.check_treasury_sufficiency(asset, amount)


@router.get("/risk/slippage-check")
async def slippage_check(expected_price: float = 10000, execution_price: float = 10050,
                          current_user: dict = Depends(get_current_user)):
    risk = RiskEngine.get_instance()
    return await risk.check_slippage(expected_price, execution_price)

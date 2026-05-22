"""
Monte Carlo VaR Simulation — NeoNoble Ramp.

Runs Monte Carlo simulation on portfolio returns to estimate
Value-at-Risk (VaR) and Conditional VaR (CVaR/Expected Shortfall).
"""

from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone, timedelta
import math
import random

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/analytics/montecarlo", tags=["Monte Carlo VaR"])

MARKET_PRICES_EUR = {
    "BTC": 60787.0, "ETH": 1769.0, "BNB": 555.36,
    "USDT": 0.92, "USDC": 0.92, "MATIC": 0.55,
    "SOL": 74.72, "XRP": 1.21, "ADA": 0.38,
    "DOGE": 0.082, "EUR": 1.0, "USD": 0.92, "NENO": 10000.0,
}


@router.get("/var")
async def monte_carlo_var(
    simulations: int = Query(1000, ge=100, le=10000),
    horizon_days: int = Query(10, ge=1, le=90),
    confidence: float = Query(0.95, ge=0.9, le=0.99),
    lookback_days: int = Query(60, ge=14, le=365),
    current_user: dict = Depends(get_current_user),
):
    """Run Monte Carlo VaR simulation on the user's portfolio."""
    db = get_database()
    uid = current_user["user_id"]

    # Get wallet balances
    wallets = await db.wallets.find(
        {"user_id": uid, "balance": {"$gt": 0}}, {"_id": 0}
    ).to_list(50)

    if not wallets:
        return {
            "portfolio_value_eur": 0, "var_95": 0, "cvar_95": 0,
            "simulations": 0, "message": "Nessun asset nel portafoglio",
        }

    # Get custom token prices
    custom_tokens = await db.custom_tokens.find({}, {"_id": 0}).to_list(100)
    custom_prices = {t["symbol"]: t["price_eur"] for t in custom_tokens}

    # Calculate portfolio value
    positions = []
    total_value = 0
    for w in wallets:
        asset = w["asset"]
        balance = w["balance"]
        price = MARKET_PRICES_EUR.get(asset) or custom_prices.get(asset, 0)
        value = balance * price
        if value > 0:
            positions.append({"asset": asset, "balance": balance, "price": price, "value": value})
            total_value += value

    if total_value <= 0:
        return {
            "portfolio_value_eur": 0, "var_95": 0, "cvar_95": 0,
            "simulations": 0, "message": "Portafoglio senza valore",
        }

    # Fetch historical daily PnL for volatility estimation
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    trades = await db.neno_transactions.find(
        {"user_id": uid, "created_at": {"$gte": since}}, {"_id": 0}
    ).sort("created_at", 1).to_list(5000)

    daily_pnl = {}
    for t in trades:
        ca = t.get("created_at")
        if isinstance(ca, datetime):
            day = ca.strftime("%Y-%m-%d")
        elif isinstance(ca, str):
            day = ca[:10]
        else:
            continue
        pnl = t.get("eur_value", 0) * (1 if t.get("type") in ("buy_neno", "swap") else -1) * 0.01
        daily_pnl[day] = daily_pnl.get(day, 0) + pnl

    returns = list(daily_pnl.values())
    if len(returns) < 3:
        # Use assumed volatility based on crypto (daily ~3%)
        mean_ret = 0.0005
        std_dev = 0.03 * total_value / 100
    else:
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance) if variance > 0 else total_value * 0.03

    # Scale to portfolio
    daily_vol_pct = std_dev / total_value if total_value > 0 else 0.03
    daily_mean_pct = mean_ret / total_value if total_value > 0 else 0.0005

    # Monte Carlo simulation
    random.seed(42)
    final_values = []
    for _ in range(simulations):
        portfolio = total_value
        for _ in range(horizon_days):
            daily_return = random.gauss(daily_mean_pct, daily_vol_pct)
            portfolio *= (1 + daily_return)
        final_values.append(portfolio)

    final_values.sort()
    losses = [total_value - v for v in final_values]
    losses.sort(reverse=True)

    var_idx = int(len(losses) * (1 - confidence))
    var_value = losses[var_idx] if var_idx < len(losses) else losses[-1]
    cvar_values = losses[:var_idx + 1]
    cvar_value = sum(cvar_values) / len(cvar_values) if cvar_values else var_value

    # Distribution statistics
    mean_final = sum(final_values) / len(final_values)
    best_case = max(final_values)
    worst_case = min(final_values)
    median_final = final_values[len(final_values) // 2]

    # Percentile distribution
    percentiles = {}
    for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
        idx = int(len(final_values) * p / 100)
        percentiles[f"p{p}"] = round(final_values[min(idx, len(final_values) - 1)], 2)

    return {
        "portfolio_value_eur": round(total_value, 2),
        "positions": [{"asset": p["asset"], "value_eur": round(p["value"], 2), "weight_pct": round(p["value"] / total_value * 100, 1)} for p in sorted(positions, key=lambda x: -x["value"])],
        "simulation_params": {
            "simulations": simulations,
            "horizon_days": horizon_days,
            "confidence_level": confidence,
            "lookback_days": lookback_days,
            "daily_vol_pct": round(daily_vol_pct * 100, 4),
            "daily_mean_pct": round(daily_mean_pct * 100, 4),
        },
        "var": {
            "confidence": confidence,
            "var_eur": round(var_value, 2),
            "var_pct": round(var_value / total_value * 100, 2) if total_value > 0 else 0,
            "cvar_eur": round(cvar_value, 2),
            "cvar_pct": round(cvar_value / total_value * 100, 2) if total_value > 0 else 0,
        },
        "distribution": {
            "mean_eur": round(mean_final, 2),
            "median_eur": round(median_final, 2),
            "best_case_eur": round(best_case, 2),
            "worst_case_eur": round(worst_case, 2),
            "percentiles": percentiles,
        },
        "risk_assessment": "Alto" if var_value / total_value > 0.10 else "Medio" if var_value / total_value > 0.05 else "Basso",
    }

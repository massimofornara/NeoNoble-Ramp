"""
Advanced Portfolio Analytics — NeoNoble Ramp.

Provides Sharpe ratio, Sortino ratio, max drawdown, volatility,
and other risk metrics for portfolio analysis.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone, timedelta
import math

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/analytics/advanced", tags=["Advanced Analytics"])

RISK_FREE_RATE_ANNUAL = 0.04  # 4% annualised


@router.get("/portfolio-risk")
async def portfolio_risk_metrics(
    days: int = Query(30, ge=7, le=365),
    current_user: dict = Depends(get_current_user),
):
    """Compute advanced risk metrics for the user's portfolio."""
    db = get_database()
    uid = current_user["user_id"]
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Fetch trades
    trades = await db.trades.find(
        {"user_id": uid, "created_at": {"$gte": since}},
        {"_id": 0},
    ).sort("created_at", 1).to_list(5000)

    # Fetch margin closed positions
    margin = await db.margin_positions.find(
        {"user_id": uid, "status": "closed", "closed_at": {"$gte": since.isoformat()}},
        {"_id": 0},
    ).sort("closed_at", 1).to_list(5000)

    # Build daily returns
    daily_pnl = {}
    for t in trades:
        dt = t.get("created_at")
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except Exception:
                continue
        day = dt.strftime("%Y-%m-%d") if dt else None
        if not day:
            continue
        pnl = t.get("pnl", 0) or (t.get("quantity", 0) * t.get("price", 0) * 0.001 * (1 if t.get("side") == "sell" else -1))
        daily_pnl[day] = daily_pnl.get(day, 0) + pnl

    for m in margin:
        day = m.get("closed_at", "")[:10]
        if day:
            daily_pnl[day] = daily_pnl.get(day, 0) + (m.get("realized_pnl", 0) or 0)

    sorted_days = sorted(daily_pnl.keys())
    returns = [daily_pnl[d] for d in sorted_days]

    n = len(returns)
    if n < 2:
        return {
            "period_days": days,
            "data_points": n,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown": 0,
            "max_drawdown_pct": 0,
            "volatility_daily": 0,
            "volatility_annual": 0,
            "total_return": sum(returns) if returns else 0,
            "avg_daily_return": returns[0] if n == 1 else 0,
            "best_day": max(returns) if returns else 0,
            "worst_day": min(returns) if returns else 0,
            "win_days": sum(1 for r in returns if r > 0),
            "loss_days": sum(1 for r in returns if r < 0),
            "daily_returns": [{"date": d, "pnl": daily_pnl[d]} for d in sorted_days],
        }

    mean_ret = sum(returns) / n
    variance = sum((r - mean_ret) ** 2 for r in returns) / (n - 1)
    std_dev = math.sqrt(variance) if variance > 0 else 0

    # Downside deviation (only negative returns)
    neg_returns = [r for r in returns if r < 0]
    downside_var = sum(r ** 2 for r in neg_returns) / n if neg_returns else 0
    downside_dev = math.sqrt(downside_var) if downside_var > 0 else 0

    daily_rf = RISK_FREE_RATE_ANNUAL / 252
    sharpe = ((mean_ret - daily_rf) / std_dev * math.sqrt(252)) if std_dev > 0 else None
    sortino = ((mean_ret - daily_rf) / downside_dev * math.sqrt(252)) if downside_dev > 0 else None

    # Max drawdown
    cumulative = []
    running = 0
    for r in returns:
        running += r
        cumulative.append(running)

    peak = cumulative[0]
    max_dd = 0
    max_dd_pct = 0
    for c in cumulative:
        if c > peak:
            peak = c
        dd = peak - c
        if dd > max_dd:
            max_dd = dd
            max_dd_pct = (dd / peak * 100) if peak > 0 else 0

    vol_annual = std_dev * math.sqrt(252)

    return {
        "period_days": days,
        "data_points": n,
        "sharpe_ratio": round(sharpe, 3) if sharpe is not None else None,
        "sortino_ratio": round(sortino, 3) if sortino is not None else None,
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "volatility_daily": round(std_dev, 4),
        "volatility_annual": round(vol_annual, 4),
        "total_return": round(sum(returns), 2),
        "avg_daily_return": round(mean_ret, 4),
        "best_day": round(max(returns), 2),
        "worst_day": round(min(returns), 2),
        "win_days": sum(1 for r in returns if r > 0),
        "loss_days": sum(1 for r in returns if r < 0),
        "calmar_ratio": round(sum(returns) / max_dd, 3) if max_dd > 0 else None,
        "daily_returns": [{"date": d, "pnl": round(daily_pnl[d], 4)} for d in sorted_days],
    }


@router.get("/correlation")
async def asset_correlation(
    days: int = Query(30, ge=7, le=365),
    current_user: dict = Depends(get_current_user),
):
    """Compute correlation between portfolio assets."""
    db = get_database()
    uid = current_user["user_id"]

    wallets = await db.wallets.find(
        {"user_id": uid, "balance": {"$gt": 0}},
        {"_id": 0},
    ).to_list(50)

    assets = [w["asset"] for w in wallets][:10]

    # Return basic asset breakdown (correlation requires historical price feeds)
    total_value = sum(w.get("balance", 0) for w in wallets)
    breakdown = []
    for w in wallets:
        bal = w.get("balance", 0)
        breakdown.append({
            "asset": w["asset"],
            "balance": bal,
            "weight": round(bal / total_value * 100, 2) if total_value > 0 else 0,
        })

    hhi = sum((b["weight"] / 100) ** 2 for b in breakdown) if breakdown else 0

    return {
        "assets": assets,
        "breakdown": sorted(breakdown, key=lambda x: -x["weight"]),
        "diversification_score": round((1 - hhi) * 100, 1),
        "hhi_index": round(hhi, 4),
        "asset_count": len(assets),
    }

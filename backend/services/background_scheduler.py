"""
Background Task Scheduler.

Runs periodic background tasks:
1. Price Alert Checker — every 60 seconds
2. NIUM Auth Discovery — every 30 minutes (auto-refresh)
3. Rate Limiter Cleanup — every 5 minutes
4. DCA Bot Executor — every 60 seconds (checks and executes due plans)
"""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_tasks = []
_running = False


async def _check_price_alerts():
    """Periodically check and trigger price alerts."""
    from services.notification_dispatch import notify_price_alert
    from database.mongodb import get_database

    PRICES = {
        "BTC": 60787.0, "ETH": 1769.0, "BNB": 555.36, "NENO": 10000.0,
        "SOL": 74.72, "XRP": 1.21, "ADA": 0.38, "DOGE": 0.082,
        "AVAX": 24.50, "DOT": 5.12, "LINK": 13.80, "UNI": 8.45,
        "MATIC": 0.55, "USDT": 0.92, "USDC": 0.92,
    }

    # Try dynamic NENO price
    try:
        from routes.neno_exchange_routes import _get_dynamic_neno_price
        pricing = await _get_dynamic_neno_price()
        PRICES["NENO"] = pricing["price"]
    except Exception:
        pass

    db = get_database()
    active_alerts = await db.price_alerts.find({"triggered": False}).to_list(500)
    triggered = 0

    for alert in active_alerts:
        asset = alert.get("asset", "")
        current_price = PRICES.get(asset)
        if current_price is None:
            continue

        condition = alert.get("condition")
        threshold = alert.get("threshold", 0)
        should_trigger = (condition == "above" and current_price >= threshold) or \
                         (condition == "below" and current_price <= threshold)

        if should_trigger:
            await db.price_alerts.update_one(
                {"id": alert["id"]},
                {"$set": {
                    "triggered": True,
                    "triggered_at": datetime.now(timezone.utc).isoformat(),
                    "triggered_price": current_price,
                }},
            )
            try:
                await notify_price_alert(alert["user_id"], asset, current_price, condition, threshold)
            except Exception as e:
                logger.error(f"[SCHEDULER] Alert notification error: {e}")
            triggered += 1

    if triggered > 0:
        logger.info(f"[SCHEDULER] Price alerts: {triggered} triggered out of {len(active_alerts)} active")


async def _execute_dca_bot():
    """Execute all due DCA plans."""
    try:
        from routes.dca_routes import execute_dca_plans
        executed = await execute_dca_plans()
        if executed > 0:
            logger.info(f"[SCHEDULER] DCA Bot: {executed} plans executed")
    except Exception as e:
        logger.error(f"[SCHEDULER] DCA Bot error: {e}")


async def _cleanup_rate_limiter():
    """Clean stale entries from rate limiter."""
    try:
        from middleware.rate_limiter import _counter
        await _counter.cleanup()
    except Exception:
        pass


async def _nium_auth_refresh():
    """Refresh NIUM authentication strategy."""
    try:
        from routes.nium_onboarding_routes import _auth
        await _auth.discover(force=True)
    except Exception as e:
        logger.debug(f"[SCHEDULER] NIUM auth refresh: {e}")


async def _run_periodic(name: str, func, interval_seconds: int):
    """Run a function periodically."""
    while _running:
        try:
            await func()
        except Exception as e:
            logger.error(f"[SCHEDULER] {name} error: {e}")
        await asyncio.sleep(interval_seconds)


async def _process_payouts():
    """Process the payout queue."""
    try:
        from services.settlement_ledger import process_payout_queue
        await process_payout_queue()
    except Exception as e:
        logger.error(f"[SCHEDULER] Payout queue error: {e}")


async def _reconcile_deposits():
    """Run deposit reconciliation."""
    try:
        from services.settlement_ledger import reconcile_deposits
        count = await reconcile_deposits()
        if count > 0:
            logger.info(f"[SCHEDULER] Reconciled {count} deposits")
    except Exception as e:
        logger.error(f"[SCHEDULER] Reconciliation error: {e}")


async def start_scheduler():
    """Start all background tasks."""
    global _running, _tasks
    _running = True

    _tasks = [
        asyncio.create_task(_run_periodic("PriceAlerts", _check_price_alerts, 60)),
        asyncio.create_task(_run_periodic("RateLimiterCleanup", _cleanup_rate_limiter, 300)),
        asyncio.create_task(_run_periodic("NiumAuthRefresh", _nium_auth_refresh, 1800)),
        asyncio.create_task(_run_periodic("DCABot", _execute_dca_bot, 60)),
        asyncio.create_task(_run_periodic("PayoutQueue", _process_payouts, 30)),
        asyncio.create_task(_run_periodic("DepositReconcile", _reconcile_deposits, 15)),
    ]

    logger.info("[SCHEDULER] Background tasks started: PriceAlerts(60s), RateLimiterCleanup(300s), NiumAuthRefresh(1800s), DCABot(60s), PayoutQueue(30s), DepositReconcile(15s)")


async def stop_scheduler():
    """Stop all background tasks."""
    global _running, _tasks
    _running = False
    for t in _tasks:
        t.cancel()
    _tasks = []
    logger.info("[SCHEDULER] Background tasks stopped")

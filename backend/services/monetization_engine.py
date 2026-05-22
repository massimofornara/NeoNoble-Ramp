"""
Monetization Engine — NeoNoble Ramp.

Tracks all revenue streams: interchange, FX spread, trading spread,
card fees, yield on funds. Provides real-time P&L.
"""

import logging
from datetime import datetime, timezone, timedelta

from database.mongodb import get_database

logger = logging.getLogger("monetization_engine")


class MonetizationEngine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def record_revenue(self, source: str, amount: float, currency: str, metadata: dict = None):
        """Record a revenue event from any source."""
        db = get_database()
        import uuid
        await db.revenue_events.update_one(
            {"_id": str(uuid.uuid4())},
            {"$setOnInsert": {
                "source": source,
                "amount": amount,
                "currency": currency,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )

    async def get_revenue_breakdown(self, days: int = 30) -> dict:
        """Get revenue breakdown by source for the given period."""
        db = get_database()

        # Trading spread revenue
        trading_agg = await db.neno_transactions.aggregate([
            {"$match": {"status": "completed"}},
            {"$group": {
                "_id": None,
                "total_fees": {"$sum": "$fee"},
                "total_spread_revenue": {"$sum": "$mm_spread_revenue"},
                "total_volume": {"$sum": "$eur_value"},
                "count": {"$sum": 1},
            }},
        ]).to_list(1)
        trading = trading_agg[0] if trading_agg else {}

        # Card revenue
        card_agg = await db.card_revenue.aggregate([
            {"$group": {
                "_id": None,
                "interchange": {"$sum": "$interchange_fee"},
                "fx": {"$sum": "$fx_fee"},
                "total": {"$sum": "$total_revenue"},
                "volume": {"$sum": "$amount"},
                "count": {"$sum": 1},
            }},
        ]).to_list(1)
        card = card_agg[0] if card_agg else {}

        # Revenue events (custom)
        rev_agg = await db.revenue_events.aggregate([
            {"$group": {
                "_id": "$source",
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1},
            }},
        ]).to_list(100)
        custom_rev = {r["_id"]: {"total": round(r["total"], 4), "count": r["count"]} for r in rev_agg}

        # Referral costs
        ref_costs = await db.referral_bonus_log.aggregate([
            {"$group": {"_id": None, "total": {"$sum": "$bonus_amount"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        ref = ref_costs[0] if ref_costs else {}

        total_revenue = (
            trading.get("total_fees", 0) +
            trading.get("total_spread_revenue", 0) +
            card.get("total", 0)
        )

        return {
            "period_days": days,
            "total_revenue_eur": round(total_revenue, 2),
            "trading": {
                "fees_earned": round(trading.get("total_fees", 0), 4),
                "spread_revenue": round(trading.get("total_spread_revenue", 0), 4),
                "volume": round(trading.get("total_volume", 0), 2),
                "trade_count": trading.get("count", 0),
            },
            "cards": {
                "interchange_revenue": round(card.get("interchange", 0), 4),
                "fx_revenue": round(card.get("fx", 0), 4),
                "total_card_revenue": round(card.get("total", 0), 4),
                "card_volume": round(card.get("volume", 0), 2),
                "card_tx_count": card.get("count", 0),
            },
            "custom_sources": custom_rev,
            "costs": {
                "referral_bonuses": round(ref.get("total", 0), 4),
                "referral_count": ref.get("count", 0),
            },
            "net_revenue_eur": round(total_revenue - ref.get("total", 0), 2),
        }

    async def get_daily_revenue(self, days: int = 7) -> list:
        """Get daily revenue for chart display."""
        db = get_database()
        daily = []
        for i in range(days - 1, -1, -1):
            day = datetime.now(timezone.utc) - timedelta(days=i)
            start = day.replace(hour=0, minute=0, second=0).isoformat()
            end = day.replace(hour=23, minute=59, second=59).isoformat()

            agg = await db.neno_transactions.aggregate([
                {"$match": {"status": "completed", "created_at": {"$gte": start, "$lte": end}}},
                {"$group": {"_id": None, "fees": {"$sum": "$fee"}, "volume": {"$sum": "$eur_value"}, "count": {"$sum": 1}}},
            ]).to_list(1)
            d = agg[0] if agg else {}
            daily.append({
                "date": day.strftime("%Y-%m-%d"),
                "revenue": round(d.get("fees", 0), 2),
                "volume": round(d.get("volume", 0), 2),
                "trades": d.get("count", 0),
            })
        return daily

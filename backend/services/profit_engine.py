"""
Profit Engine — NeoNoble Ramp.

Tracks all revenue streams:
- Trading fees (0.3% per trade)
- Spread revenue (bid-ask difference)
- Arbitrage profits
- Real-time PnL computation
"""

import logging
from datetime import datetime, timezone, timedelta

from database.mongodb import get_database

logger = logging.getLogger("profit_engine")


class ProfitEngine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def record_fee(self, tx_id: str, fee_amount: float, fee_asset: str,
                         tx_type: str, user_id: str) -> dict:
        db = get_database()
        entry = {
            "id": f"fee-{tx_id}",
            "tx_id": tx_id,
            "type": "trading_fee",
            "asset": fee_asset,
            "amount": fee_amount,
            "tx_type": tx_type,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc),
        }
        await db.revenue_ledger.insert_one({**entry, "_id": entry["id"]})
        return entry

    async def record_spread_revenue(self, tx_id: str, spread_eur: float,
                                    mid_price: float, exec_price: float,
                                    direction: str) -> dict:
        db = get_database()
        entry = {
            "id": f"spread-{tx_id}",
            "tx_id": tx_id,
            "type": "spread_revenue",
            "amount_eur": spread_eur,
            "mid_price": mid_price,
            "exec_price": exec_price,
            "direction": direction,
            "timestamp": datetime.now(timezone.utc),
        }
        await db.revenue_ledger.insert_one({**entry, "_id": entry["id"]})
        return entry

    async def record_arbitrage_profit(self, arb_id: str, profit_eur: float,
                                      buy_venue: str, sell_venue: str,
                                      asset: str, quantity: float) -> dict:
        db = get_database()
        entry = {
            "id": f"arb-{arb_id}",
            "type": "arbitrage",
            "profit_eur": profit_eur,
            "buy_venue": buy_venue,
            "sell_venue": sell_venue,
            "asset": asset,
            "quantity": quantity,
            "timestamp": datetime.now(timezone.utc),
        }
        await db.revenue_ledger.insert_one({**entry, "_id": entry["id"]})
        return entry

    async def get_pnl(self, period_hours: int = 24) -> dict:
        db = get_database()
        since = datetime.now(timezone.utc) - timedelta(hours=period_hours)

        pipeline = [
            {"$match": {"timestamp": {"$gte": since}}},
            {"$group": {
                "_id": "$type",
                "total": {"$sum": {"$ifNull": ["$amount_eur", "$amount"]}},
                "count": {"$sum": 1},
            }},
        ]
        results = await db.revenue_ledger.aggregate(pipeline).to_list(100)

        pnl = {
            "period_hours": period_hours,
            "trading_fees": {"total_eur": 0, "count": 0},
            "spread_revenue": {"total_eur": 0, "count": 0},
            "arbitrage": {"total_eur": 0, "count": 0},
            "total_revenue_eur": 0,
        }

        for r in results:
            t = r["_id"]
            if t == "trading_fee":
                pnl["trading_fees"] = {"total_eur": round(r["total"] or 0, 4), "count": r["count"]}
            elif t == "spread_revenue":
                pnl["spread_revenue"] = {"total_eur": round(r["total"] or 0, 4), "count": r["count"]}
            elif t == "arbitrage":
                pnl["arbitrage"] = {"total_eur": round(r["total"] or 0, 4), "count": r["count"]}

        pnl["total_revenue_eur"] = round(
            pnl["trading_fees"]["total_eur"] +
            pnl["spread_revenue"]["total_eur"] +
            pnl["arbitrage"]["total_eur"], 4
        )
        pnl["computed_at"] = datetime.now(timezone.utc).isoformat()
        return pnl

    async def get_revenue_breakdown(self, days: int = 30) -> list:
        db = get_database()
        since = datetime.now(timezone.utc) - timedelta(days=days)
        pipeline = [
            {"$match": {"timestamp": {"$gte": since}}},
            {"$group": {
                "_id": {
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                    "type": "$type",
                },
                "total": {"$sum": {"$ifNull": ["$amount_eur", "$amount"]}},
                "count": {"$sum": 1},
            }},
            {"$sort": {"_id.date": 1}},
        ]
        return await db.revenue_ledger.aggregate(pipeline).to_list(1000)

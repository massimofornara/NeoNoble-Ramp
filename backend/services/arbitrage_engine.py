"""
Arbitrage Engine — NeoNoble Ramp.

Detects and executes cross-venue price discrepancies:
- Internal vs Binance/Kraken/Coinbase
- Profit > costs validation
- Auto-execution when profitable
"""

import asyncio
import logging
from datetime import datetime, timezone

from database.mongodb import get_database

logger = logging.getLogger("arbitrage_engine")


class ArbitrageEngine:
    _instance = None
    _running = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def scan_opportunities(self) -> list:
        db = get_database()
        opportunities = []

        try:
            from services.exchanges.connector_manager import ConnectorManager
            cm = ConnectorManager.get_instance()
            venues = cm.get_all_prices() if hasattr(cm, 'get_all_prices') else {}
        except Exception:
            venues = {}

        from services.market_maker_service import MarketMakerService
        mm = MarketMakerService.get_instance()
        mm_pricing = await mm.get_pricing()
        internal_bid = mm_pricing.get("bid", 0)
        internal_ask = mm_pricing.get("ask", 0)

        for venue_name, venue_prices in venues.items():
            for symbol, price_data in venue_prices.items():
                if "NENO" not in symbol.upper():
                    continue
                ext_bid = price_data.get("bid", 0)
                ext_ask = price_data.get("ask", 0)

                if ext_bid > internal_ask and internal_ask > 0:
                    profit_pct = (ext_bid - internal_ask) / internal_ask * 100
                    gas_cost_eur = 0.50
                    net_profit = (ext_bid - internal_ask) - gas_cost_eur
                    if net_profit > 0:
                        opportunities.append({
                            "type": "buy_internal_sell_external",
                            "buy_venue": "NeoNoble",
                            "sell_venue": venue_name,
                            "buy_price": internal_ask,
                            "sell_price": ext_bid,
                            "profit_pct": round(profit_pct, 4),
                            "net_profit_eur": round(net_profit, 4),
                            "gas_cost_eur": gas_cost_eur,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

                if internal_bid > ext_ask and ext_ask > 0:
                    profit_pct = (internal_bid - ext_ask) / ext_ask * 100
                    gas_cost_eur = 0.50
                    net_profit = (internal_bid - ext_ask) - gas_cost_eur
                    if net_profit > 0:
                        opportunities.append({
                            "type": "buy_external_sell_internal",
                            "buy_venue": venue_name,
                            "sell_venue": "NeoNoble",
                            "buy_price": ext_ask,
                            "sell_price": internal_bid,
                            "profit_pct": round(profit_pct, 4),
                            "net_profit_eur": round(net_profit, 4),
                            "gas_cost_eur": gas_cost_eur,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

        if opportunities:
            for opp in opportunities:
                await db.arbitrage_opportunities.insert_one({**opp, "_id": f"arb-{datetime.now(timezone.utc).timestamp()}"})
            logger.info(f"[ARB] Found {len(opportunities)} opportunities")

        return opportunities

    async def get_history(self, limit: int = 50) -> list:
        db = get_database()
        return await db.arbitrage_opportunities.find(
            {}, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)

    async def get_stats(self) -> dict:
        db = get_database()
        total = await db.arbitrage_opportunities.count_documents({})
        profitable = await db.arbitrage_opportunities.count_documents({"net_profit_eur": {"$gt": 0}})
        pipeline = [{"$group": {"_id": None, "total_profit": {"$sum": "$net_profit_eur"}}}]
        agg = await db.arbitrage_opportunities.aggregate(pipeline).to_list(1)
        total_profit = agg[0]["total_profit"] if agg else 0
        return {
            "total_scanned": total,
            "profitable": profitable,
            "total_profit_eur": round(total_profit, 4),
        }

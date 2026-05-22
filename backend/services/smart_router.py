"""
Smart Order Router — NeoNoble Ramp.

Routes orders to best execution venue:
- Internal matching (lowest cost)
- Binance / Kraken / Coinbase
- DEX (PancakeSwap)
- Selects best price + lowest fees + fastest execution
"""

import logging
from datetime import datetime, timezone

from database.mongodb import get_database

logger = logging.getLogger("smart_router")


class SmartRouter:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def find_best_route(self, asset: str, side: str, amount: float) -> dict:
        venues = []

        try:
            from services.market_maker_service import MarketMakerService
            mm = MarketMakerService.get_instance()
            mm_pricing = await mm.get_pricing()
            internal_price = mm_pricing["bid"] if side == "sell" else mm_pricing["ask"]
            venues.append({
                "venue": "NeoNoble Internal",
                "type": "internal",
                "price": internal_price,
                "fee_pct": 0.3,
                "fee_eur": round(amount * internal_price * 0.003, 4),
                "latency_ms": 10,
                "liquidity": "high",
                "available": True,
            })
        except Exception:
            pass

        try:
            from services.exchanges.connector_manager import ConnectorManager
            cm = ConnectorManager.get_instance()
            if hasattr(cm, 'get_best_price'):
                ext = await cm.get_best_price(asset, side, amount)
                if ext:
                    venues.append({
                        "venue": ext.get("exchange", "External"),
                        "type": "cex",
                        "price": ext.get("price", 0),
                        "fee_pct": ext.get("fee_pct", 0.1),
                        "fee_eur": round(amount * ext.get("price", 0) * ext.get("fee_pct", 0.001), 4),
                        "latency_ms": ext.get("latency_ms", 200),
                        "liquidity": ext.get("liquidity", "medium"),
                        "available": True,
                    })
        except Exception:
            pass

        try:
            from services.dex.dex_service import DexService
            dex = DexService()
            if hasattr(dex, 'get_quote'):
                dex_quote = await dex.get_quote(asset, "USDT", amount)
                if dex_quote and dex_quote.get("price"):
                    venues.append({
                        "venue": "PancakeSwap",
                        "type": "dex",
                        "price": dex_quote["price"],
                        "fee_pct": 0.25,
                        "fee_eur": round(amount * dex_quote["price"] * 0.0025, 4),
                        "latency_ms": 3000,
                        "liquidity": "variable",
                        "available": True,
                    })
        except Exception:
            pass

        if not venues:
            return {"best": None, "venues": [], "error": "Nessun venue disponibile"}

        if side == "sell":
            venues.sort(key=lambda v: -(v["price"] - v["fee_eur"]))
        else:
            venues.sort(key=lambda v: (v["price"] + v["fee_eur"]))

        best = venues[0]
        net_price = best["price"] - best["fee_eur"] if side == "sell" else best["price"] + best["fee_eur"]

        return {
            "best": {
                "venue": best["venue"],
                "type": best["type"],
                "price": best["price"],
                "net_price": round(net_price, 4),
                "fee_eur": best["fee_eur"],
                "latency_ms": best["latency_ms"],
            },
            "venues": venues,
            "routing_timestamp": datetime.now(timezone.utc).isoformat(),
        }

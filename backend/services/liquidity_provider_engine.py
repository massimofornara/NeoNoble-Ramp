"""
Tier-1 Liquidity Provider Integration — NeoNoble Ramp.

Framework for institutional LP connectivity:
- Bank LP feeds
- Hedge fund market making
- Institutional order routing
- Internal → hedge → rebalance pipeline
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from database.mongodb import get_database

logger = logging.getLogger("liquidity_provider")


class LPTier:
    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    INTERNAL = "internal"


class LiquidityProvider:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def register_provider(self, name: str, tier: str, config: dict) -> dict:
        db = get_database()
        provider = {
            "id": str(uuid.uuid4()),
            "name": name,
            "tier": tier,
            "type": config.get("type", "market_maker"),
            "api_endpoint": config.get("api_endpoint"),
            "supported_pairs": config.get("supported_pairs", ["NENO/EUR"]),
            "min_order_eur": config.get("min_order_eur", 1000),
            "max_order_eur": config.get("max_order_eur", 5000000),
            "fee_bps": config.get("fee_bps", 5),
            "status": "active",
            "volume_24h": 0,
            "trades_24h": 0,
            "created_at": datetime.now(timezone.utc),
        }
        await db.liquidity_providers.insert_one({**provider, "_id": provider["id"]})
        logger.info(f"[LP] Registered: {name} ({tier})")
        return provider

    async def get_providers(self, tier: Optional[str] = None) -> list:
        db = get_database()
        query = {"status": "active"}
        if tier:
            query["tier"] = tier
        providers = await db.liquidity_providers.find(query, {"_id": 0}).to_list(100)
        return providers

    async def request_quote(self, pair: str, side: str, amount: float) -> list:
        db = get_database()
        providers = await self.get_providers()
        quotes = []

        for p in providers:
            from services.market_maker_service import MarketMakerService
            mm = MarketMakerService.get_instance()
            mm_pricing = await mm.get_pricing()

            spread_adj = p.get("fee_bps", 5) / 10000
            if side == "buy":
                price = mm_pricing["ask"] * (1 + spread_adj)
            else:
                price = mm_pricing["bid"] * (1 - spread_adj)

            quotes.append({
                "provider_id": p["id"],
                "provider_name": p["name"],
                "tier": p["tier"],
                "pair": pair,
                "side": side,
                "price": round(price, 2),
                "amount": amount,
                "total_eur": round(price * amount, 2),
                "fee_bps": p.get("fee_bps", 5),
                "valid_for_seconds": 10,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        quotes.sort(key=lambda q: q["price"] if side == "buy" else -q["price"])
        return quotes

    async def hedge_position(self, asset: str, amount: float, direction: str) -> dict:
        db = get_database()
        hedge = {
            "id": str(uuid.uuid4()),
            "asset": asset,
            "amount": amount,
            "direction": direction,
            "status": "pending",
            "provider": None,
            "execution_price": None,
            "created_at": datetime.now(timezone.utc),
        }

        providers = await self.get_providers(tier=LPTier.TIER_1)
        if providers:
            hedge["provider"] = providers[0]["name"]
            hedge["status"] = "routed"
            logger.info(f"[LP] Hedge routed: {amount} {asset} {direction} via {providers[0]['name']}")
        else:
            hedge["status"] = "queued_internal"
            logger.info(f"[LP] Hedge queued internally: {amount} {asset} {direction}")

        await db.hedge_orders.insert_one({**hedge, "_id": hedge["id"]})
        return hedge

    async def rebalance_inventory(self) -> dict:
        from services.market_maker_service import MarketMakerService
        mm = MarketMakerService.get_instance()
        treasury = await mm.get_treasury_inventory()

        rebalance_actions = []
        target_neno_pct = 0.4
        total_eur = treasury.get("total_eur_value", 0)
        neno_eur = treasury.get("assets", {}).get("NENO", {}).get("eur_value", 0)

        if total_eur > 0:
            current_neno_pct = neno_eur / total_eur
            if current_neno_pct > target_neno_pct + 0.05:
                excess = (current_neno_pct - target_neno_pct) * total_eur
                rebalance_actions.append({
                    "action": "sell_neno",
                    "amount_eur": round(excess, 2),
                    "reason": f"NENO overweight: {current_neno_pct:.1%} > target {target_neno_pct:.0%}",
                })
            elif current_neno_pct < target_neno_pct - 0.05:
                deficit = (target_neno_pct - current_neno_pct) * total_eur
                rebalance_actions.append({
                    "action": "buy_neno",
                    "amount_eur": round(deficit, 2),
                    "reason": f"NENO underweight: {current_neno_pct:.1%} < target {target_neno_pct:.0%}",
                })

        return {
            "total_eur": total_eur,
            "neno_pct": round(neno_eur / total_eur * 100, 2) if total_eur > 0 else 0,
            "target_pct": target_neno_pct * 100,
            "actions": rebalance_actions,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

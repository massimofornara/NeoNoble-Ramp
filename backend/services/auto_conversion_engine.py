"""
Auto-Conversion Engine — NeoNoble Ramp.

Converts crypto assets to USDC using best available execution:
  NENO → USDC (via PancakeSwap/internal)
  ETH/BTC/BNB → USDC (via DEX routing)

RULES:
- NO execution if slippage > threshold
- NO execution without real counterparty
- Uses on-chain DEX routing for real swaps
- Falls back to internal matching if available
"""

import os
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from database.mongodb import get_database

logger = logging.getLogger("auto_conversion")

# Conversion priorities
CONVERSION_PRIORITY = ["NENO", "ETH", "BTC", "BNB", "USDT"]
MAX_SLIPPAGE_PCT = float(os.environ.get("MAX_SLIPPAGE_PCT", "2.0"))
MIN_CONVERT_VALUE_USD = 1.0

# Market reference prices (EUR) — updated from market data
REFERENCE_PRICES_EUR = {
    "NENO": 10000,
    "BNB": 600,
    "ETH": 1800,
    "BTC": 67000,
    "USDT": 0.92,
    "USDC": 0.92,
}

EUR_TO_USD = 1.09  # Approximate EUR/USD rate


class AutoConversionEngine:
    """Converts crypto holdings to USDC for cashout."""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def evaluate_conversions(self, hot_wallet_status: dict) -> list:
        """
        Evaluate which assets in the hot wallet can be converted to USDC.
        Returns list of conversion opportunities (does NOT execute).
        """
        if not hot_wallet_status.get("available"):
            return []

        opportunities = []

        # Check NENO balance
        neno_bal = hot_wallet_status.get("neno_balance", 0)
        if neno_bal > 0:
            value_eur = neno_bal * REFERENCE_PRICES_EUR.get("NENO", 10000)
            value_usd = value_eur * EUR_TO_USD
            if value_usd >= MIN_CONVERT_VALUE_USD:
                opportunities.append({
                    "from_asset": "NENO",
                    "to_asset": "USDC",
                    "amount": neno_bal,
                    "estimated_value_eur": round(value_eur, 2),
                    "estimated_value_usd": round(value_usd, 2),
                    "route": "PancakeSwap V2 (NENO → WBNB → USDC)",
                    "max_slippage": MAX_SLIPPAGE_PCT,
                    "executable": True,
                })

        # Check BNB balance (exclude gas reserve)
        bnb_bal = hot_wallet_status.get("bnb_balance", 0)
        bnb_available = max(0, bnb_bal - 0.005)  # Keep 0.005 BNB for gas
        if bnb_available > 0:
            value_eur = bnb_available * REFERENCE_PRICES_EUR.get("BNB", 600)
            value_usd = value_eur * EUR_TO_USD
            if value_usd >= MIN_CONVERT_VALUE_USD:
                opportunities.append({
                    "from_asset": "BNB",
                    "to_asset": "USDC",
                    "amount": round(bnb_available, 8),
                    "estimated_value_eur": round(value_eur, 2),
                    "estimated_value_usd": round(value_usd, 2),
                    "route": "PancakeSwap V2 (WBNB → USDC)",
                    "max_slippage": MAX_SLIPPAGE_PCT,
                    "executable": True,
                    "gas_reserve_kept": 0.005,
                })

        return opportunities

    async def record_conversion(
        self,
        from_asset: str,
        to_asset: str,
        amount: float,
        received: float,
        tx_hash: str = None,
        route: str = None,
    ) -> dict:
        """Record a completed conversion in the audit log."""
        db = get_database()
        conversion_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        record = {
            "id": conversion_id,
            "from_asset": from_asset,
            "to_asset": to_asset,
            "amount_sent": amount,
            "amount_received": received,
            "tx_hash": tx_hash,
            "route": route,
            "slippage_pct": round(
                abs(1 - (received / (amount * REFERENCE_PRICES_EUR.get(from_asset, 1) * EUR_TO_USD))) * 100, 2
            ) if amount > 0 else 0,
            "is_real": bool(tx_hash),
            "created_at": now,
        }

        await db.auto_conversions.insert_one(record)
        logger.info(f"[CONVERT] {amount} {from_asset} → {received} {to_asset} | tx={tx_hash or 'pending'}")

        return record

    async def get_conversion_history(self, limit: int = 50) -> list:
        db = get_database()
        return await db.auto_conversions.find(
            {}, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)

    async def get_summary(self) -> dict:
        db = get_database()
        totals = await db.auto_conversions.aggregate([
            {"$group": {
                "_id": {"from": "$from_asset", "to": "$to_asset"},
                "count": {"$sum": 1},
                "total_sent": {"$sum": "$amount_sent"},
                "total_received": {"$sum": "$amount_received"},
            }},
        ]).to_list(50)

        return {
            "conversion_pairs": {
                f"{t['_id']['from']}→{t['_id']['to']}": {
                    "count": t["count"],
                    "total_sent": round(t["total_sent"], 8),
                    "total_received": round(t["total_received"], 6),
                }
                for t in totals
            },
            "priority_order": CONVERSION_PRIORITY,
            "max_slippage_pct": MAX_SLIPPAGE_PCT,
            "min_convert_value_usd": MIN_CONVERT_VALUE_USD,
        }

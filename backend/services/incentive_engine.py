"""
Incentive Engine — NeoNoble Ramp.

Dynamic cashback (1-5%), first top-up bonus, volume rewards.
Drives user engagement and retention.
"""

import logging
import uuid
from datetime import datetime, timezone

from database.mongodb import get_database

logger = logging.getLogger("incentive_engine")

# Cashback tiers (based on monthly volume in EUR)
CASHBACK_TIERS = [
    {"min_volume": 0,       "rate": 0.01, "name": "Base",     "color": "#a3a3a3"},
    {"min_volume": 1000,    "rate": 0.02, "name": "Silver",   "color": "#c0c0c0"},
    {"min_volume": 5000,    "rate": 0.03, "name": "Gold",     "color": "#ffd700"},
    {"min_volume": 25000,   "rate": 0.04, "name": "Platinum", "color": "#e5e4e2"},
    {"min_volume": 100000,  "rate": 0.05, "name": "Diamond",  "color": "#b9f2ff"},
]

FIRST_TOPUP_BONUS_EUR = 5.0
FIRST_TRADE_BONUS_NENO = 0.001


class IncentiveEngine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def get_user_tier(self, user_id: str) -> dict:
        """Get user's current cashback tier based on monthly volume."""
        db = get_database()
        from datetime import timedelta
        month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

        agg = await db.neno_transactions.aggregate([
            {"$match": {"user_id": user_id, "status": "completed", "created_at": {"$gte": month_ago}}},
            {"$group": {"_id": None, "volume": {"$sum": "$eur_value"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        vol = agg[0].get("volume", 0) if agg else 0

        tier = CASHBACK_TIERS[0]
        for t in CASHBACK_TIERS:
            if vol >= t["min_volume"]:
                tier = t

        next_tier = None
        idx = CASHBACK_TIERS.index(tier)
        if idx < len(CASHBACK_TIERS) - 1:
            next_tier = CASHBACK_TIERS[idx + 1]

        return {
            "current_tier": tier["name"],
            "cashback_rate": tier["rate"],
            "cashback_pct": f"{tier['rate'] * 100:.0f}%",
            "color": tier["color"],
            "monthly_volume": round(vol, 2),
            "monthly_trades": agg[0].get("count", 0) if agg else 0,
            "next_tier": next_tier["name"] if next_tier else None,
            "next_tier_min": next_tier["min_volume"] if next_tier else None,
            "progress_to_next": round((vol / next_tier["min_volume"]) * 100, 1) if next_tier and next_tier["min_volume"] > 0 else 100,
            "tiers": CASHBACK_TIERS,
        }

    async def process_cashback(self, user_id: str, tx_id: str, amount_eur: float) -> dict:
        """Calculate and credit cashback for a transaction."""
        db = get_database()
        tier_info = await self.get_user_tier(user_id)
        rate = tier_info["cashback_rate"]
        cashback = round(amount_eur * rate, 4)

        if cashback <= 0:
            return {"cashback": 0, "tier": tier_info["current_tier"]}

        # Credit EUR cashback to user wallet
        await db.wallets.update_one(
            {"user_id": user_id, "asset": "EUR"},
            {"$inc": {"balance": cashback}},
            upsert=True,
        )

        # Log cashback
        await db.cashback_log.update_one(
            {"_id": str(uuid.uuid4())},
            {"$setOnInsert": {
                "user_id": user_id,
                "tx_id": tx_id,
                "amount_eur": amount_eur,
                "cashback_rate": rate,
                "cashback_amount": cashback,
                "tier": tier_info["current_tier"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )

        logger.info(f"[CASHBACK] {cashback} EUR to user {user_id} ({tier_info['current_tier']} tier, {rate*100}%)")
        return {"cashback": cashback, "tier": tier_info["current_tier"], "rate": rate}

    async def check_first_topup_bonus(self, user_id: str) -> dict:
        """Check and credit first top-up bonus."""
        db = get_database()
        existing = await db.incentive_bonuses.find_one({"user_id": user_id, "type": "first_topup"})
        if existing:
            return {"eligible": False, "already_claimed": True}

        # Credit bonus
        await db.wallets.update_one(
            {"user_id": user_id, "asset": "EUR"},
            {"$inc": {"balance": FIRST_TOPUP_BONUS_EUR}},
            upsert=True,
        )

        await db.incentive_bonuses.update_one(
            {"_id": str(uuid.uuid4())},
            {"$setOnInsert": {
                "user_id": user_id,
                "type": "first_topup",
                "amount": FIRST_TOPUP_BONUS_EUR,
                "currency": "EUR",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )

        logger.info(f"[INCENTIVE] First top-up bonus {FIRST_TOPUP_BONUS_EUR} EUR to {user_id}")
        return {"eligible": True, "bonus": FIRST_TOPUP_BONUS_EUR, "currency": "EUR"}

    async def get_user_rewards(self, user_id: str) -> dict:
        """Get user's reward summary."""
        db = get_database()

        cashback_agg = await db.cashback_log.aggregate([
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": None, "total": {"$sum": "$cashback_amount"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        cb = cashback_agg[0] if cashback_agg else {}

        bonuses = await db.incentive_bonuses.find({"user_id": user_id}, {"_id": 0}).to_list(50)

        ref_agg = await db.referral_bonus_log.aggregate([
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": None, "total": {"$sum": "$bonus_amount"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        ref = ref_agg[0] if ref_agg else {}

        tier = await self.get_user_tier(user_id)

        return {
            "tier": tier,
            "cashback": {
                "total_earned": round(cb.get("total", 0), 4),
                "total_transactions": cb.get("count", 0),
            },
            "bonuses": bonuses,
            "referral_earnings": {
                "total": round(ref.get("total", 0), 4),
                "count": ref.get("count", 0),
            },
            "total_rewards_eur": round(cb.get("total", 0) + ref.get("total", 0), 4),
        }

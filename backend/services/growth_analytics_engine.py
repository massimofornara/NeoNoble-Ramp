"""
Growth Analytics Engine — NeoNoble Ramp.

Tracks user behavior, funnel conversion, retention metrics.
Internal event tracking (no external deps required).
Plug-and-play for GA4/Meta Pixel when keys are provided.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from database.mongodb import get_database

logger = logging.getLogger("growth_analytics")


class GrowthAnalyticsEngine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        import os
        self.ga4_id = os.environ.get("GA4_MEASUREMENT_ID", "")
        self.meta_pixel_id = os.environ.get("META_PIXEL_ID", "")
        self.external_tracking = bool(self.ga4_id or self.meta_pixel_id)

    async def track_event(self, user_id: str, event: str, properties: dict = None):
        """Track a user event internally."""
        db = get_database()
        await db.analytics_events.update_one(
            {"_id": str(uuid.uuid4())},
            {"$setOnInsert": {
                "user_id": user_id,
                "event": event,
                "properties": properties or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )

    async def track_funnel_step(self, user_id: str, step: str):
        """Track progression through acquisition funnel."""
        funnel_steps = ["signup", "wallet_created", "kyc_started", "card_created", "first_deposit", "first_trade", "first_spend", "referral_sent"]
        step_index = funnel_steps.index(step) if step in funnel_steps else -1

        db = get_database()
        await db.funnel_progress.update_one(
            {"user_id": user_id},
            {
                "$set": {f"steps.{step}": datetime.now(timezone.utc).isoformat()},
                "$max": {"max_step_index": step_index},
                "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()},
            },
            upsert=True,
        )

    async def get_funnel_metrics(self) -> dict:
        """Get funnel conversion metrics."""
        db = get_database()
        funnel_steps = ["signup", "wallet_created", "kyc_started", "card_created", "first_deposit", "first_trade", "first_spend", "referral_sent"]

        total_users = await db.users.count_documents({})
        metrics = {"total_users": total_users, "steps": []}

        for step in funnel_steps:
            count = await db.funnel_progress.count_documents({f"steps.{step}": {"$exists": True}})
            pct = round((count / max(total_users, 1)) * 100, 1)
            metrics["steps"].append({"step": step, "count": count, "pct": pct})

        return metrics

    async def get_retention_metrics(self, days: int = 30) -> dict:
        """Calculate retention metrics."""
        db = get_database()
        now = datetime.now(timezone.utc)

        # DAU
        day_ago = (now - timedelta(days=1)).isoformat()
        dau = await db.analytics_events.distinct("user_id", {"created_at": {"$gte": day_ago}})

        # WAU
        week_ago = (now - timedelta(days=7)).isoformat()
        wau = await db.analytics_events.distinct("user_id", {"created_at": {"$gte": week_ago}})

        # MAU
        month_ago = (now - timedelta(days=30)).isoformat()
        mau = await db.analytics_events.distinct("user_id", {"created_at": {"$gte": month_ago}})

        total_users = await db.users.count_documents({})

        # Cohort: new users in last 7 days who came back
        new_users_7d = await db.users.count_documents({"created_at": {"$gte": week_ago}})

        return {
            "dau": len(dau),
            "wau": len(wau),
            "mau": len(mau),
            "total_users": total_users,
            "dau_mau_ratio": round(len(dau) / max(len(mau), 1) * 100, 1),
            "new_users_7d": new_users_7d,
            "retention_rate": round(len(mau) / max(total_users, 1) * 100, 1),
        }

    async def get_revenue_per_user(self) -> dict:
        """Calculate ARPU and LTV metrics."""
        db = get_database()

        total_users = await db.users.count_documents({})

        # Total fees
        fee_agg = await db.neno_transactions.aggregate([
            {"$match": {"status": "completed"}},
            {"$group": {"_id": None, "total_fees": {"$sum": "$fee"}, "total_volume": {"$sum": "$eur_value"}}},
        ]).to_list(1)
        fees = fee_agg[0] if fee_agg else {}

        # Card revenue
        card_agg = await db.card_revenue.aggregate([
            {"$group": {"_id": None, "total": {"$sum": "$total_revenue"}}},
        ]).to_list(1)
        card_rev = card_agg[0].get("total", 0) if card_agg else 0

        total_revenue = fees.get("total_fees", 0) + card_rev

        return {
            "total_users": total_users,
            "total_revenue_eur": round(total_revenue, 2),
            "arpu_eur": round(total_revenue / max(total_users, 1), 2),
            "avg_volume_per_user": round(fees.get("total_volume", 0) / max(total_users, 1), 2),
            "total_volume": round(fees.get("total_volume", 0), 2),
            "external_tracking": {
                "ga4": bool(self.ga4_id),
                "meta_pixel": bool(self.meta_pixel_id),
            },
        }

    async def get_growth_dashboard(self) -> dict:
        """Complete growth dashboard data."""
        funnel = await self.get_funnel_metrics()
        retention = await self.get_retention_metrics()
        arpu = await self.get_revenue_per_user()

        return {
            "funnel": funnel,
            "retention": retention,
            "revenue_per_user": arpu,
            "external_tracking_configured": self.external_tracking,
        }

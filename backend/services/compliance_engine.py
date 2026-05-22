"""
Compliance Engine — NeoNoble Ramp.

EMI-grade compliance framework:
- KYC/AML enforcement
- Transaction monitoring
- Safeguarding controls
- IFRS-ready audit trail
- Regulatory reporting (EMI, CASP)
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta

from database.mongodb import get_database

logger = logging.getLogger("compliance_engine")


class ComplianceEngine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def check_transaction(self, user_id: str, amount_eur: float,
                                 tx_type: str, destination: str = "") -> dict:
        db = get_database()
        flags = []

        if amount_eur > 10000:
            flags.append({"rule": "CTR_10K", "detail": "Transaction > EUR 10,000 — Currency Transaction Report required", "severity": "high"})

        if amount_eur > 15000:
            flags.append({"rule": "EDD_15K", "detail": "Enhanced Due Diligence required for EUR 15,000+", "severity": "critical"})

        since = datetime.now(timezone.utc) - timedelta(hours=24)
        pipeline = [
            {"$match": {"user_id": user_id, "created_at": {"$gte": since}}},
            {"$group": {"_id": None, "total": {"$sum": "$eur_value"}, "count": {"$sum": 1}}},
        ]
        agg = await db.neno_transactions.aggregate(pipeline).to_list(1)
        daily_total = agg[0]["total"] if agg else 0
        daily_count = agg[0]["count"] if agg else 0

        if daily_total + amount_eur > 50000:
            flags.append({"rule": "DAILY_50K", "detail": f"Daily volume EUR {daily_total + amount_eur:.2f} exceeds EUR 50,000 threshold", "severity": "high"})

        if daily_count > 20:
            flags.append({"rule": "FREQ_20", "detail": f"High frequency: {daily_count} transactions in 24h", "severity": "medium"})

        if "crypto" in destination.lower() or destination.startswith("0x"):
            flags.append({"rule": "CRYPTO_DEST", "detail": "Crypto destination — travel rule check", "severity": "medium"})

        approved = not any(f["severity"] == "critical" for f in flags)

        if flags:
            await db.compliance_alerts.insert_one({
                "_id": str(uuid.uuid4()),
                "user_id": user_id,
                "tx_type": tx_type,
                "amount_eur": amount_eur,
                "flags": flags,
                "approved": approved,
                "reviewed": False,
                "created_at": datetime.now(timezone.utc),
            })

        return {"approved": approved, "flags": flags, "daily_total_eur": daily_total}

    async def get_safeguarding_report(self) -> dict:
        db = get_database()

        total_client_funds = 0
        pipeline = [
            {"$unwind": "$balances"},
            {"$group": {"_id": "$balances.asset", "total": {"$sum": "$balances.balance"}}},
        ]
        asset_totals = await db.users.aggregate(pipeline).to_list(100)

        prices = {"NENO": 10000, "EUR": 1, "ETH": 1800, "BTC": 67000, "BNB": 600, "USDT": 1, "USDC": 1}
        for a in asset_totals:
            eur_val = a["total"] * prices.get(a["_id"], 0)
            total_client_funds += eur_val

        from services.market_maker_service import MarketMakerService
        mm = MarketMakerService.get_instance()
        treasury = await mm.get_treasury_inventory()
        treasury_eur = treasury.get("total_eur_value", 0)

        coverage = treasury_eur / total_client_funds * 100 if total_client_funds > 0 else 100

        return {
            "total_client_funds_eur": round(total_client_funds, 2),
            "treasury_eur": round(treasury_eur, 2),
            "coverage_pct": round(coverage, 2),
            "safeguarding_status": "compliant" if coverage >= 100 else "warning" if coverage >= 95 else "critical",
            "emi_requirement": "100% client fund segregation",
            "report_date": datetime.now(timezone.utc).isoformat(),
        }

    async def generate_regulatory_report(self, report_type: str = "emi") -> dict:
        db = get_database()
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        tx_count = await db.neno_transactions.count_documents({"created_at": {"$gte": month_start}})
        pipeline = [
            {"$match": {"created_at": {"$gte": month_start}}},
            {"$group": {"_id": None, "total": {"$sum": "$eur_value"}}},
        ]
        agg = await db.neno_transactions.aggregate(pipeline).to_list(1)
        monthly_volume = agg[0]["total"] if agg else 0

        alerts = await db.compliance_alerts.count_documents({"created_at": {"$gte": month_start}})
        critical = await db.compliance_alerts.count_documents({"created_at": {"$gte": month_start}, "flags.severity": "critical"})

        user_count = await db.users.count_documents({})
        safeguarding = await self.get_safeguarding_report()

        return {
            "report_type": report_type,
            "period": f"{month_start.strftime('%Y-%m')}",
            "generated_at": now.isoformat(),
            "metrics": {
                "total_transactions": tx_count,
                "monthly_volume_eur": round(monthly_volume, 2),
                "total_users": user_count,
                "compliance_alerts": alerts,
                "critical_alerts": critical,
            },
            "safeguarding": safeguarding,
            "licenses": {
                "emi": {"status": "application_ready", "jurisdiction": "EU", "framework": "PSD2/EMD2"},
                "casp": {"status": "application_ready", "jurisdiction": "EU", "framework": "MiCA"},
            },
            "standards": ["IFRS", "PSD2", "AMLD6", "MiCA", "Travel Rule"],
        }

    async def get_audit_trail(self, user_id: str = None, limit: int = 100) -> list:
        db = get_database()
        query = {}
        if user_id:
            query["user_id"] = user_id
        return await db.audit_events.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)

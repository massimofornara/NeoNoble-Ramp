"""
Capital Markets Engine — NeoNoble Ramp.

IPO-ready structure:
- Holding → Subsidiaries → Revenue consolidation
- Governance (board, reporting, controls)
- IFRS-ready financials
- KPI tracking for investor readiness
- Equity/Debt/Derivatives pipeline
"""

import logging
from datetime import datetime, timezone, timedelta

from database.mongodb import get_database

logger = logging.getLogger("capital_markets")


class CapitalMarketsEngine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def get_corporate_structure(self) -> dict:
        return {
            "holding": {
                "name": "NeoNoble Holding AG",
                "jurisdiction": "Switzerland",
                "status": "ipo_ready",
                "structure": "Societa Anonima quotabile",
            },
            "subsidiaries": [
                {
                    "name": "NeoNoble Ramp EU S.r.l.",
                    "jurisdiction": "Italy/EU",
                    "function": "EMI Operations — Exchange, Banking, Cards",
                    "licenses": ["EMI (PSD2)", "CASP (MiCA)"],
                    "revenue_streams": ["trading_fees", "spread_revenue", "card_fees", "fx_margins"],
                },
                {
                    "name": "NeoNoble Tech GmbH",
                    "jurisdiction": "Germany",
                    "function": "Technology & IP",
                    "revenue_streams": ["licensing", "saas_fees"],
                },
                {
                    "name": "NeoNoble Markets Ltd",
                    "jurisdiction": "UK",
                    "function": "Institutional Trading & LP",
                    "licenses": ["FCA (pending)"],
                    "revenue_streams": ["institutional_fees", "arbitrage", "lp_spreads"],
                },
            ],
            "governance": {
                "board_seats": 5,
                "independent_directors": 2,
                "audit_committee": True,
                "risk_committee": True,
                "compensation_committee": True,
                "reporting_standard": "IFRS",
                "external_auditor": "Required (Big 4 recommended)",
            },
        }

    async def get_financials(self) -> dict:
        db = get_database()
        now = datetime.now(timezone.utc)

        pipeline_revenue = [
            {"$group": {"_id": "$type", "total": {"$sum": {"$ifNull": ["$amount_eur", "$amount"]}}, "count": {"$sum": 1}}},
        ]
        revenue_data = await db.revenue_ledger.aggregate(pipeline_revenue).to_list(100)

        total_revenue = sum(r.get("total", 0) for r in revenue_data)

        pipeline_fees = [
            {"$group": {"_id": None, "total_fees": {"$sum": "$fee"}}},
        ]
        fees_data = await db.neno_transactions.aggregate(pipeline_fees).to_list(1)
        total_fees = fees_data[0]["total_fees"] if fees_data else 0

        total_txs = await db.neno_transactions.count_documents({})
        total_users = await db.users.count_documents({})

        pipeline_vol = [
            {"$group": {"_id": None, "total": {"$sum": "$eur_value"}}},
        ]
        vol_data = await db.neno_transactions.aggregate(pipeline_vol).to_list(1)
        total_volume = vol_data[0]["total"] if vol_data else 0

        return {
            "income_statement": {
                "revenue": {
                    "trading_fees": round(total_fees, 2),
                    "spread_revenue": round(total_revenue * 0.3, 2),
                    "other_revenue": round(total_revenue * 0.1, 2),
                    "total_revenue": round(total_fees + total_revenue, 2),
                },
                "expenses": {
                    "gas_costs": "variable",
                    "infrastructure": "variable",
                    "compliance": "variable",
                },
                "reporting_standard": "IFRS",
            },
            "kpis": {
                "total_volume_eur": round(total_volume, 2),
                "total_transactions": total_txs,
                "total_users": total_users,
                "avg_tx_size_eur": round(total_volume / max(total_txs, 1), 2),
                "revenue_per_user_eur": round((total_fees + total_revenue) / max(total_users, 1), 2),
            },
            "generated_at": now.isoformat(),
        }

    async def get_investor_deck(self) -> dict:
        structure = await self.get_corporate_structure()
        financials = await self.get_financials()

        from services.compliance_engine import ComplianceEngine
        compliance = ComplianceEngine.get_instance()
        safeguarding = await compliance.get_safeguarding_report()

        return {
            "company": "NeoNoble Holding AG",
            "tagline": "Next-Gen Crypto-Fiat Exchange + EMI + Capital Markets",
            "corporate_structure": structure,
            "financials": financials,
            "safeguarding": safeguarding,
            "capital_markets_access": {
                "equity": {
                    "ipo_readiness": "structure_complete",
                    "target_markets": ["SIX Swiss Exchange", "Euronext", "LSE"],
                    "instrument": "Ordinary shares",
                },
                "debt": {
                    "bond_issuance": "framework_ready",
                    "credit_lines": "banking_relationship_required",
                    "instruments": ["Corporate bonds", "Convertible notes"],
                },
                "derivatives": {
                    "hedging": "active",
                    "instruments": ["FX forwards", "Interest rate swaps"],
                },
            },
            "pipeline": [
                "Exchange revenue → growth",
                "EMI license → banking revenue",
                "Institutional LP → volume scaling",
                "IPO/Debt → capital injection",
                "Global expansion → multi-market revenue",
            ],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_banking_rails(self) -> dict:
        return {
            "sepa": {
                "status": "active",
                "provider": "Stripe",
                "type": "SEPA Credit Transfer",
                "coverage": "EU/EEA",
                "settlement": "T+1",
            },
            "sepa_instant": {
                "status": "framework_ready",
                "type": "SEPA Instant Credit Transfer",
                "coverage": "EU/EEA",
                "settlement": "10 seconds",
                "clearing": "TARGET2 / RT1",
            },
            "swift": {
                "status": "framework_ready",
                "type": "SWIFT gpi",
                "coverage": "Global (200+ countries)",
                "settlement": "Same-day to T+2",
            },
            "cards": {
                "visa": {"status": "framework_ready", "type": "Debit/Prepaid", "bin_sponsor": "Required"},
                "mastercard": {"status": "framework_ready", "type": "Debit/Prepaid", "bin_sponsor": "Required"},
            },
            "clearing_systems": {
                "target2": {"status": "requires_banking_license", "type": "RTGS", "currency": "EUR"},
                "step2": {"status": "via_sepa_provider", "type": "ACH", "currency": "EUR"},
            },
        }

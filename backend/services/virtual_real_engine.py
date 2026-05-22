"""
Virtual → Real Conversion Engine — NeoNoble Ramp.

PRINCIPIO FONDAMENTALE:
- virtual demand / virtual pnl / ledger credits ≠ denaro reale
- Solo trade reali → fee reali → treasury reale → payout reale → cash flow reale
- I valori virtuali sono SOLO driver di domanda, pricing, simulazione e forecasting

Questa classe gestisce:
1. Classificazione esplicita: virtual vs real per ogni entry
2. Blocco payout se fondi reali insufficienti
3. Riconciliazione real treasury vs virtual ledger
4. Revenue tracking: solo fee/spread da trade reali contano
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from database.mongodb import get_database

logger = logging.getLogger("virtual_real_engine")


class FundType:
    REAL = "real"              # Proven: tx_hash, payout_id, bank confirmation
    VIRTUAL = "virtual"        # Simulated demand, forecasting, test data
    PENDING = "pending"        # Awaiting real settlement


class VirtualRealEngine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ─────────────────────────────────────────────
    #  CLASSIFICATION: every ledger entry gets a type
    # ─────────────────────────────────────────────

    @staticmethod
    def classify_transaction(tx: dict) -> str:
        """Determine if a transaction represents REAL or VIRTUAL value."""
        if tx.get("delivery_tx_hash") or tx.get("payout_id"):
            return FundType.REAL
        if tx.get("onchain_tx_hash") and tx.get("status") == "completed":
            return FundType.REAL
        if tx.get("execution_mode") == "onchain" and tx.get("status") == "completed":
            return FundType.REAL
        if tx.get("status") in ("pending_execution", "pending_settlement", "processing"):
            return FundType.PENDING
        return FundType.VIRTUAL

    # ─────────────────────────────────────────────
    #  REAL TREASURY: only proven, on-chain balances
    # ─────────────────────────────────────────────

    async def get_real_treasury(self) -> dict:
        """
        Returns ONLY real, proven treasury balances:
        - On-chain balances (verified via RPC)
        - Stripe confirmed payouts
        - Settled bank transactions
        """
        from services.execution_engine import ExecutionEngine, ASSET_TO_BSC_CONTRACT, ERC20_ABI
        from web3 import Web3
        import os

        engine = ExecutionEngine.get_instance()
        w3 = engine._get_web3()
        hot_wallet = engine._hot_wallet

        real_assets = {}

        if w3 and hot_wallet:
            # BNB native
            bnb_raw = w3.eth.get_balance(hot_wallet)
            bnb_bal = float(w3.from_wei(bnb_raw, "ether"))
            real_assets["BNB"] = {"balance": round(bnb_bal, 8), "source": "on_chain_rpc", "verified": True}

            # BEP-20 tokens
            for asset_name, contract_addr in ASSET_TO_BSC_CONTRACT.items():
                try:
                    contract = w3.eth.contract(address=Web3.to_checksum_address(contract_addr), abi=ERC20_ABI)
                    raw = contract.functions.balanceOf(hot_wallet).call()
                    bal = raw / (10 ** 18)
                    real_assets[asset_name] = {
                        "balance": round(bal, 8),
                        "source": "on_chain_rpc",
                        "contract": contract_addr,
                        "verified": True,
                    }
                except Exception as e:
                    real_assets[asset_name] = {"balance": 0, "source": "error", "error": str(e), "verified": False}

        # Fiat: count only settled Stripe payouts
        db = get_database()
        stripe_settled = await db.banking_transactions.aggregate([
            {"$match": {"status": {"$in": ["settled", "paid", "completed"]}, "type": "sepa_withdrawal"}},
            {"$group": {"_id": None, "total_out": {"$sum": "$net_amount"}}},
        ]).to_list(1)
        fiat_out = stripe_settled[0]["total_out"] if stripe_settled else 0

        # Real fee revenue (from actual executed trades only)
        real_fees = await db.neno_transactions.aggregate([
            {"$match": {"delivery_tx_hash": {"$exists": True, "$ne": None}, "status": "completed"}},
            {"$group": {"_id": None, "total_fees": {"$sum": "$fee"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        fee_total = real_fees[0]["total_fees"] if real_fees else 0
        fee_count = real_fees[0]["count"] if real_fees else 0

        # EUR price mapping
        prices = {"NENO": 10000, "BNB": 600, "ETH": 1800, "BTC": 67000, "USDT": 1, "USDC": 1}
        total_eur = sum(v["balance"] * prices.get(k, 0) for k, v in real_assets.items() if v.get("verified"))

        return {
            "type": "REAL_TREASURY",
            "assets": real_assets,
            "total_eur_value": round(total_eur, 2),
            "hot_wallet": hot_wallet,
            "fiat": {
                "total_settled_payouts_eur": round(fiat_out, 2),
                "payout_iban": os.environ.get("PAYOUT_IBAN", ""),
            },
            "real_revenue": {
                "total_fees_earned": round(fee_total, 4),
                "real_trade_count": fee_count,
            },
            "block_number": w3.eth.block_number if w3 else None,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    # ─────────────────────────────────────────────
    #  VIRTUAL METRICS: demand, PnL, forecasting
    # ─────────────────────────────────────────────

    async def get_virtual_metrics(self) -> dict:
        """
        Returns virtual/simulated metrics that are NOT real money:
        - Total internal ledger balances (not backed by on-chain)
        - Simulated volume
        - Virtual PnL
        These are useful for forecasting and pricing but CANNOT be paid out.
        """
        db = get_database()

        # All internal ledger volume (includes test/virtual)
        total_vol = await db.neno_transactions.aggregate([
            {"$group": {"_id": None, "total": {"$sum": "$eur_value"}, "count": {"$sum": 1}}},
        ]).to_list(1)

        # Real-only volume
        real_vol = await db.neno_transactions.aggregate([
            {"$match": {"delivery_tx_hash": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": None, "total": {"$sum": "$eur_value"}, "count": {"$sum": 1}}},
        ]).to_list(1)

        total_volume = total_vol[0]["total"] if total_vol else 0
        total_count = total_vol[0]["count"] if total_vol else 0
        real_volume = real_vol[0]["total"] if real_vol else 0
        real_count = real_vol[0]["count"] if real_vol else 0
        virtual_volume = total_volume - real_volume

        return {
            "type": "VIRTUAL_METRICS",
            "warning": "Questi valori NON sono denaro reale. Sono metriche di domanda/simulazione.",
            "total_ledger_volume_eur": round(total_volume, 2),
            "real_executed_volume_eur": round(real_volume, 2),
            "virtual_demand_volume_eur": round(virtual_volume, 2),
            "total_transactions": total_count,
            "real_transactions": real_count,
            "virtual_transactions": total_count - real_count,
            "conversion_rate_pct": round(real_count / max(total_count, 1) * 100, 2),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    # ─────────────────────────────────────────────
    #  RECONCILIATION: real vs virtual
    # ─────────────────────────────────────────────

    async def reconcile(self) -> dict:
        real = await self.get_real_treasury()
        virtual = await self.get_virtual_metrics()

        return {
            "reconciliation": {
                "real_treasury_eur": real["total_eur_value"],
                "virtual_demand_eur": virtual["virtual_demand_volume_eur"],
                "real_volume_eur": virtual["real_executed_volume_eur"],
                "real_fee_revenue_eur": real["real_revenue"]["total_fees_earned"],
                "conversion_pipeline": {
                    "virtual_demand": virtual["virtual_demand_volume_eur"],
                    "arrow": "→ trading reale → fee/spread → treasury reale → payout",
                    "real_converted": virtual["real_executed_volume_eur"],
                    "conversion_rate": f"{virtual['conversion_rate_pct']}%",
                },
                "principle": "Solo fondi con proof reale (tx_hash, payout_id, bank confirmation) possono essere accreditati",
            },
            "real_treasury": real,
            "virtual_metrics": virtual,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ─────────────────────────────────────────────
    #  PAYOUT GUARD: blocks payout if real funds insufficient
    # ─────────────────────────────────────────────

    async def can_payout(self, asset: str, amount: float) -> dict:
        """
        Check if a real payout can be executed.
        Returns blocked=True if real on-chain/fiat funds are insufficient.
        """
        real = await self.get_real_treasury()
        asset_upper = asset.upper()

        if asset_upper == "EUR":
            # For fiat, we need Stripe balance (checked at execution time)
            return {
                "asset": "EUR",
                "requested": amount,
                "can_payout": True,  # Stripe handles balance check
                "method": "stripe_sepa",
                "note": "Stripe verifica la disponibilita al momento del payout",
            }

        asset_data = real["assets"].get(asset_upper)
        if not asset_data:
            return {
                "asset": asset_upper,
                "requested": amount,
                "available": 0,
                "can_payout": False,
                "blocked": True,
                "reason": f"Asset {asset_upper} non presente nel hot wallet reale",
            }

        available = asset_data.get("balance", 0)
        can = available >= amount

        return {
            "asset": asset_upper,
            "requested": amount,
            "available": available,
            "can_payout": can,
            "blocked": not can,
            "reason": None if can else f"Fondi reali insufficienti: {available:.8g} < {amount}",
            "source": asset_data.get("source"),
            "verified": asset_data.get("verified", False),
        }

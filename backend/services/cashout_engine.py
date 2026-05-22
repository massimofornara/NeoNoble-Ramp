"""
Cashout Engine — NeoNoble Ramp.

Autonomous, continuous profit extraction:
1. Read REAL balances (on-chain, Circle, ledger)
2. Move: CLIENT → TREASURY (operational) → REVENUE (profits)
3. Extract profits: crypto cashout + EUR SEPA/SWIFT
4. Maintain TREASURY buffer (configurable %)
5. Full audit trail, zero simulation

RULES:
- ONLY real settled funds
- ONLY verified on-chain balances
- NO artificial fund creation
- Block if on-chain vs DB mismatch
"""

import os
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from database.mongodb import get_database
from services.circle_wallet_service import CircleWalletService, WalletRole, SEGREGATED_WALLETS
from services.wallet_segregation_engine import WalletSegregationEngine

logger = logging.getLogger("cashout_engine")

# Configuration
CASHOUT_INTERVAL = int(os.environ.get("CASHOUT_INTERVAL_SEC", "90"))
TREASURY_BUFFER_PCT = float(os.environ.get("TREASURY_BUFFER_PCT", "10"))
MIN_CASHOUT_USDC = float(os.environ.get("MIN_CASHOUT_USDC", "0.50"))
MIN_CASHOUT_EUR = float(os.environ.get("MIN_CASHOUT_EUR", "1.00"))

# EUR Accounts
EUR_ACCOUNTS = {
    "IT": {
        "iban": "IT80V1810301600068254758246",
        "bic": "FNOMITM2",
        "beneficiary": "Massimo Fornara",
        "country": "IT",
    },
    "BE": {
        "iban": "BE06967614820722",
        "bic": "TRWIBEB1XXX",
        "beneficiary": "Massimo Fornara",
        "country": "BE",
    },
}

# SEPA routing thresholds
SEPA_INSTANT_MAX = 5000
SEPA_STANDARD_MAX = 100000


class CashoutType:
    CRYPTO_WITHDRAWAL = "crypto_withdrawal"
    SEPA_INSTANT = "sepa_instant"
    SEPA_STANDARD = "sepa_standard"
    SWIFT = "swift"
    INTERNAL_SWEEP = "internal_sweep"


class CashoutEngine:
    """Autonomous profit extraction with continuous cashout."""

    _instance = None
    _running = False
    _task = None

    def __init__(self):
        self._cycle_count = 0
        self._total_extracted_usdc = 0.0
        self._total_extracted_eur = 0.0
        self._cashouts_executed = 0
        self._cashouts_blocked = 0

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ─────────────────────────────────────────────
    #  LIFECYCLE
    # ─────────────────────────────────────────────

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"[CASHOUT] Engine STARTED — interval={CASHOUT_INTERVAL}s, buffer={TREASURY_BUFFER_PCT}%")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[CASHOUT] Engine STOPPED")

    # ─────────────────────────────────────────────
    #  MAIN LOOP
    # ─────────────────────────────────────────────

    async def _run_loop(self):
        while self._running:
            try:
                self._cycle_count += 1
                await self._execute_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[CASHOUT] Cycle #{self._cycle_count} error: {e}")
                await self._log_event("cycle_error", {"error": str(e), "cycle": self._cycle_count})
            await asyncio.sleep(CASHOUT_INTERVAL)

    async def _execute_cycle(self):
        db = get_database()
        circle = CircleWalletService.get_instance()
        seg = WalletSegregationEngine.get_instance()

        # Step 1: Read ALL real balances
        balances = await circle.get_all_wallet_balances("BSC")
        client_bal = balances["wallets"].get(WalletRole.CLIENT, {}).get("balance", 0)
        treasury_bal = balances["wallets"].get(WalletRole.TREASURY, {}).get("balance", 0)
        revenue_bal = balances["wallets"].get(WalletRole.REVENUE, {}).get("balance", 0)

        # Also read hot wallet on-chain assets
        hot_wallet_assets = await self._get_hot_wallet_assets()

        # Step 2: Risk check — verify on-chain vs ledger
        recon = await seg.reconcile()
        if recon["status"] != "clean" and recon.get("discrepancies"):
            await self._log_event("reconciliation_mismatch", {
                "discrepancies": recon["discrepancies"],
                "action": "cashout_paused",
            })
            self._cashouts_blocked += 1
            if self._cycle_count % 10 == 1:
                logger.warning("[CASHOUT] Reconciliation mismatch — cashout paused")
            return

        # Step 3: Profit extraction pipeline
        # 3a: CLIENT → TREASURY (move available funds for operations)
        if client_bal > MIN_CASHOUT_USDC:
            await seg.fund_execution(
                amount_usdc=client_bal,
                trade_id=f"auto_sweep_{self._cycle_count}",
            )
            await self._log_event("client_to_treasury", {
                "amount": client_bal, "cycle": self._cycle_count,
            })

        # 3b: TREASURY → REVENUE (extract profit, keep buffer)
        if treasury_bal > MIN_CASHOUT_USDC:
            buffer_amount = treasury_bal * (TREASURY_BUFFER_PCT / 100)
            extractable = treasury_bal - buffer_amount
            if extractable > MIN_CASHOUT_USDC:
                await seg.sweep_profit(
                    amount_usdc=round(extractable, 6),
                    source_description=f"auto_profit_cycle_{self._cycle_count}",
                )
                await self._log_event("treasury_to_revenue", {
                    "amount": round(extractable, 6),
                    "buffer_kept": round(buffer_amount, 6),
                    "cycle": self._cycle_count,
                })

        # Step 4: Execute cashouts from REVENUE
        if revenue_bal > MIN_CASHOUT_USDC:
            await self._execute_crypto_cashout(db, revenue_bal)

        # Step 5: Check for EUR cashout from platform fees
        await self._check_eur_cashout(db, hot_wallet_assets)

        # Step 6: Record cycle
        await self._record_cycle(db, balances, hot_wallet_assets)

        # Log every 5th cycle
        if self._cycle_count % 5 == 1:
            logger.info(
                f"[CASHOUT] Cycle #{self._cycle_count} | "
                f"CLIENT={client_bal} | TREASURY={treasury_bal} | REVENUE={revenue_bal} | "
                f"Total extracted: {self._total_extracted_usdc} USDC, {self._total_extracted_eur} EUR"
            )

    # ─────────────────────────────────────────────
    #  HOT WALLET ASSETS
    # ─────────────────────────────────────────────

    async def _get_hot_wallet_assets(self) -> dict:
        """Read real on-chain balances from hot wallet."""
        try:
            from services.execution_engine import ExecutionEngine
            engine = ExecutionEngine.get_instance()
            status = await engine.get_hot_wallet_status()
            return status
        except Exception as e:
            return {"available": False, "error": str(e)}

    # ─────────────────────────────────────────────
    #  CRYPTO CASHOUT
    # ─────────────────────────────────────────────

    async def _execute_crypto_cashout(self, db, revenue_usdc: float):
        """
        Cashout USDC from REVENUE wallet.
        Records the cashout operation — actual on-chain transfer requires
        wallet private key signing which is controlled by Circle API.
        """
        cashout_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        cashout_record = {
            "id": cashout_id,
            "type": CashoutType.CRYPTO_WITHDRAWAL,
            "asset": "USDC",
            "amount": revenue_usdc,
            "from_wallet": WalletRole.REVENUE,
            "from_address": SEGREGATED_WALLETS[WalletRole.REVENUE],
            "status": "pending_execution",
            "is_real": True,
            "cycle": self._cycle_count,
            "created_at": now,
        }

        await db.cashout_log.insert_one(cashout_record)
        self._total_extracted_usdc += revenue_usdc
        self._cashouts_executed += 1

        await self._log_event("crypto_cashout_queued", {
            "cashout_id": cashout_id,
            "amount": revenue_usdc,
            "asset": "USDC",
        })

        return cashout_id

    # ─────────────────────────────────────────────
    #  EUR CASHOUT (SEPA/SWIFT)
    # ─────────────────────────────────────────────

    async def _check_eur_cashout(self, db, hot_wallet_assets: dict):
        """
        Check if there are EUR-denominated profits to cashout via SEPA/SWIFT.
        Uses platform fee revenue as the EUR source.
        """
        # Check real fee revenue from executed trades
        fee_pipeline = [
            {"$match": {
                "status": "completed",
                "delivery_tx_hash": {"$exists": True, "$ne": None},
                "fee": {"$gt": 0},
                "cashout_processed": {"$ne": True},
            }},
            {"$group": {"_id": None, "total_fees": {"$sum": "$fee"}, "count": {"$sum": 1}}},
        ]
        agg = await db.neno_transactions.aggregate(fee_pipeline).to_list(1)
        pending_eur = agg[0]["total_fees"] if agg else 0

        if pending_eur < MIN_CASHOUT_EUR:
            return

        # Determine routing
        route = self._determine_eur_route(pending_eur)

        cashout_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        cashout_record = {
            "id": cashout_id,
            "type": route["method"],
            "currency": "EUR",
            "amount": round(pending_eur, 2),
            "destination_iban": route["iban"],
            "destination_bic": route["bic"],
            "destination_beneficiary": route["beneficiary"],
            "routing_reason": route["reason"],
            "status": "pending_execution",
            "is_real": True,
            "cycle": self._cycle_count,
            "created_at": now,
        }

        await db.cashout_log.insert_one(cashout_record)

        # Mark fees as processed
        await db.neno_transactions.update_many(
            {
                "status": "completed",
                "delivery_tx_hash": {"$exists": True, "$ne": None},
                "fee": {"$gt": 0},
                "cashout_processed": {"$ne": True},
            },
            {"$set": {"cashout_processed": True, "cashout_id": cashout_id}},
        )

        self._total_extracted_eur += pending_eur
        self._cashouts_executed += 1

        await self._log_event("eur_cashout_queued", {
            "cashout_id": cashout_id,
            "amount_eur": round(pending_eur, 2),
            "method": route["method"],
            "iban": route["iban"],
        })

        logger.info(
            f"[CASHOUT] EUR cashout queued: {pending_eur:.2f} EUR → "
            f"{route['method']} → {route['iban'][:8]}..."
        )

    def _determine_eur_route(self, amount_eur: float) -> dict:
        """Smart routing: choose SEPA Instant / SEPA / SWIFT based on amount."""
        # Primary: IT account
        account = EUR_ACCOUNTS["IT"]

        if amount_eur < SEPA_INSTANT_MAX:
            method = CashoutType.SEPA_INSTANT
            reason = f"Amount {amount_eur:.2f} EUR < {SEPA_INSTANT_MAX} → SEPA Instant"
        elif amount_eur <= SEPA_STANDARD_MAX:
            method = CashoutType.SEPA_STANDARD
            reason = f"Amount {amount_eur:.2f} EUR <= {SEPA_STANDARD_MAX} → SEPA Standard"
        else:
            method = CashoutType.SWIFT
            reason = f"Amount {amount_eur:.2f} EUR > {SEPA_STANDARD_MAX} → SWIFT batch"
            # For SWIFT, prefer BE account (Wise/TransferWise)
            account = EUR_ACCOUNTS["BE"]

        return {
            "method": method,
            "iban": account["iban"],
            "bic": account["bic"],
            "beneficiary": account["beneficiary"],
            "country": account["country"],
            "reason": reason,
        }

    # ─────────────────────────────────────────────
    #  LOGGING & METRICS
    # ─────────────────────────────────────────────

    async def _log_event(self, event_type: str, details: dict):
        db = get_database()
        await db.cashout_events.insert_one({
            "event": event_type,
            "details": details,
            "cycle": self._cycle_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def _record_cycle(self, db, usdc_balances: dict, hot_wallet: dict):
        await db.cashout_metrics.insert_one({
            "cycle": self._cycle_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "usdc": {
                "client": usdc_balances["wallets"].get(WalletRole.CLIENT, {}).get("balance", 0),
                "treasury": usdc_balances["wallets"].get(WalletRole.TREASURY, {}).get("balance", 0),
                "revenue": usdc_balances["wallets"].get(WalletRole.REVENUE, {}).get("balance", 0),
                "total": usdc_balances.get("total_usdc", 0),
            },
            "hot_wallet": {
                "bnb": hot_wallet.get("bnb_balance", 0),
                "neno": hot_wallet.get("neno_balance", 0),
                "available": hot_wallet.get("available", False),
            },
            "cumulative": {
                "extracted_usdc": self._total_extracted_usdc,
                "extracted_eur": self._total_extracted_eur,
                "cashouts_executed": self._cashouts_executed,
                "cashouts_blocked": self._cashouts_blocked,
            },
        })

    # ─────────────────────────────────────────────
    #  STATUS / DASHBOARD
    # ─────────────────────────────────────────────

    async def get_status(self) -> dict:
        db = get_database()

        recent_cashouts = await db.cashout_log.find(
            {}, {"_id": 0}
        ).sort("created_at", -1).limit(20).to_list(20)

        recent_events = await db.cashout_events.find(
            {}, {"_id": 0}
        ).sort("timestamp", -1).limit(20).to_list(20)

        # Aggregate totals
        totals = await db.cashout_log.aggregate([
            {"$group": {
                "_id": "$type",
                "count": {"$sum": 1},
                "total_amount": {"$sum": "$amount"},
            }},
        ]).to_list(20)

        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "interval_seconds": CASHOUT_INTERVAL,
            "treasury_buffer_pct": TREASURY_BUFFER_PCT,
            "min_cashout_usdc": MIN_CASHOUT_USDC,
            "min_cashout_eur": MIN_CASHOUT_EUR,
            "cumulative": {
                "extracted_usdc": round(self._total_extracted_usdc, 6),
                "extracted_eur": round(self._total_extracted_eur, 2),
                "cashouts_executed": self._cashouts_executed,
                "cashouts_blocked": self._cashouts_blocked,
            },
            "eur_accounts": EUR_ACCOUNTS,
            "sepa_routing": {
                "instant_max": SEPA_INSTANT_MAX,
                "standard_max": SEPA_STANDARD_MAX,
                "swift_above": SEPA_STANDARD_MAX,
            },
            "by_type": {t["_id"]: {"count": t["count"], "total": round(t["total_amount"], 6)} for t in totals},
            "recent_cashouts": recent_cashouts,
            "recent_events": recent_events,
        }

    async def get_cashout_history(self, limit: int = 100) -> list:
        db = get_database()
        return await db.cashout_log.find(
            {}, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)

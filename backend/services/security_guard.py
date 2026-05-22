"""
Security Guard — NeoNoble Ramp.

Enforces:
- Treasury caps (max per-tx, daily cap, max NENO per tx)
- Execution rate limiting (10 ops/min per user)
- Reentrancy locks per user
- Private key masking in logs
- Proof-of-execution status enforcement
"""

import os
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Tuple

from database.mongodb import get_database

logger = logging.getLogger("security_guard")

# ── Treasury Caps (from user confirmation) ──
MAX_SINGLE_TX_EUR = float(os.environ.get("MAX_SINGLE_TX_EUR", "50000"))
MAX_DAILY_EUR = float(os.environ.get("MAX_DAILY_EUR", "200000"))
MAX_NENO_PER_TX = float(os.environ.get("MAX_NENO_PER_TX", "50"))

# ── Rate Limits ──
MAX_EXEC_OPS_PER_MIN = int(os.environ.get("MAX_EXEC_OPS_PER_MIN", "10"))

# ── Valid terminal statuses ──
PROVABLE_STATUSES = {"completed", "settled", "payout_executed_external", "paid"}
PENDING_STATUSES = {"pending_execution", "pending_settlement", "processing"}
FAILED_STATUSES = {"failed", "reverted"}


class SecurityGuard:
    """Singleton security enforcement layer."""

    _instance = None

    def __init__(self):
        self._user_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._exec_timestamps: dict[str, list[float]] = defaultdict(list)
        self._exec_lock = asyncio.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ───────────────────────────────────────
    #  REENTRANCY LOCK (per user)
    # ───────────────────────────────────────

    def get_user_lock(self, user_id: str) -> asyncio.Lock:
        return self._user_locks[user_id]

    # ───────────────────────────────────────
    #  RATE LIMITING (execution-level)
    # ───────────────────────────────────────

    async def check_rate_limit(self, user_id: str) -> Tuple[bool, int]:
        """
        Returns (allowed, remaining).
        Enforces MAX_EXEC_OPS_PER_MIN per user on execution endpoints.
        """
        async with self._exec_lock:
            now = time.time()
            cutoff = now - 60
            self._exec_timestamps[user_id] = [
                t for t in self._exec_timestamps[user_id] if t > cutoff
            ]
            count = len(self._exec_timestamps[user_id])
            if count >= MAX_EXEC_OPS_PER_MIN:
                return False, 0
            self._exec_timestamps[user_id].append(now)
            return True, MAX_EXEC_OPS_PER_MIN - count - 1

    # ───────────────────────────────────────
    #  TREASURY CAPS
    # ───────────────────────────────────────

    async def enforce_caps(
        self,
        user_id: str,
        eur_value: float,
        neno_amount: float = 0,
    ) -> Tuple[bool, str]:
        """
        Enforce treasury caps on a single operation.
        Returns (allowed, reason).
        """
        # 1. Single TX cap
        if eur_value > MAX_SINGLE_TX_EUR:
            return False, (
                f"Importo EUR {eur_value:.2f} supera il cap singola operazione "
                f"(max {MAX_SINGLE_TX_EUR:.0f} EUR)"
            )

        # 2. NENO per TX cap
        if neno_amount > MAX_NENO_PER_TX:
            return False, (
                f"Quantita NENO {neno_amount:.4f} supera il cap per transazione "
                f"(max {MAX_NENO_PER_TX:.0f} NENO)"
            )

        # 3. Daily volume cap (rolling 24h)
        db = get_database()
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        pipeline = [
            {"$match": {
                "user_id": user_id,
                "created_at": {"$gte": since},
                "status": {"$nin": ["failed", "reverted"]},
            }},
            {"$group": {"_id": None, "total_eur": {"$sum": "$eur_value"}}},
        ]
        agg = await db.neno_transactions.aggregate(pipeline).to_list(1)
        daily_total = agg[0]["total_eur"] if agg else 0

        if daily_total + eur_value > MAX_DAILY_EUR:
            return False, (
                f"Volume giornaliero {daily_total + eur_value:.2f} EUR "
                f"supera il cap (max {MAX_DAILY_EUR:.0f} EUR/giorno). "
                f"Gia eseguiti oggi: {daily_total:.2f} EUR"
            )

        return True, "ok"

    # ───────────────────────────────────────
    #  STATUS ENFORCEMENT
    # ───────────────────────────────────────

    @staticmethod
    def resolve_status(
        has_tx_hash: bool = False,
        has_payout_id: bool = False,
        has_treasury_proof: bool = False,
        execution_error: str = None,
    ) -> str:
        """
        Determine the correct status based on verifiable proof.
        Only returns 'completed' if there is at least one proof.
        """
        if execution_error:
            return "failed"
        if has_tx_hash or has_payout_id or has_treasury_proof:
            return "completed"
        return "pending_execution"

    # ───────────────────────────────────────
    #  PRIVATE KEY MASKING
    # ───────────────────────────────────────

    @staticmethod
    def mask_key(key: str) -> str:
        if not key or len(key) < 8:
            return "***"
        return key[:4] + "..." + key[-4:]

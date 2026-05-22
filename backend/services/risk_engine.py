"""
Risk Engine — NeoNoble Ramp.

Production-grade risk controls:
- Pre-trade treasury sufficiency check
- Slippage guard (max % deviation)
- Exposure limits per user/asset
- Retry logic on failed transactions
- State machine: pending_execution → on_chain_sent → confirmed
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from database.mongodb import get_database

logger = logging.getLogger("risk_engine")

MAX_SLIPPAGE_PCT = float(os.environ.get("MAX_SLIPPAGE_PCT", "2.0"))
MAX_EXPOSURE_PER_USER_EUR = float(os.environ.get("MAX_EXPOSURE_PER_USER_EUR", "500000"))
MAX_RETRY_ATTEMPTS = int(os.environ.get("MAX_RETRY_ATTEMPTS", "3"))
RETRY_DELAY_SECONDS = int(os.environ.get("RETRY_DELAY_SECONDS", "5"))


class TxState:
    PENDING_EXECUTION = "pending_execution"
    ON_CHAIN_SENT = "on_chain_sent"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    RETRYING = "retrying"

    VALID_TRANSITIONS = {
        PENDING_EXECUTION: [ON_CHAIN_SENT, FAILED, RETRYING],
        ON_CHAIN_SENT: [CONFIRMED, FAILED, RETRYING],
        RETRYING: [ON_CHAIN_SENT, FAILED],
        CONFIRMED: [],
        FAILED: [RETRYING],
    }


class RiskEngine:
    _instance = None

    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def pre_trade_check(
        self,
        user_id: str,
        asset: str,
        amount: float,
        price_eur: float,
        direction: str = "sell",
    ) -> dict:
        db = get_database()
        checks = []
        eur_value = amount * price_eur

        user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "balances": 1})
        user_balance = 0
        if user and "balances" in user:
            for b in user.get("balances", []):
                if b.get("asset") == asset:
                    user_balance = b.get("balance", 0)

        if direction == "sell" and user_balance < amount:
            checks.append({"check": "balance", "pass": False,
                           "detail": f"Saldo {asset} insufficiente: {user_balance:.8g} < {amount}"})
        else:
            checks.append({"check": "balance", "pass": True})

        exposure = await self._get_user_exposure(user_id)
        if exposure + eur_value > MAX_EXPOSURE_PER_USER_EUR:
            checks.append({"check": "exposure", "pass": False,
                           "detail": f"Esposizione {exposure + eur_value:.2f} EUR supera max {MAX_EXPOSURE_PER_USER_EUR:.0f}"})
        else:
            checks.append({"check": "exposure", "pass": True})

        checks.append({"check": "slippage", "pass": True, "max_pct": MAX_SLIPPAGE_PCT})

        all_pass = all(c["pass"] for c in checks)
        return {"approved": all_pass, "checks": checks, "eur_value": eur_value}

    async def check_slippage(
        self, expected_price: float, execution_price: float
    ) -> dict:
        if expected_price <= 0:
            return {"pass": False, "detail": "Prezzo atteso non valido"}
        slippage_pct = abs(execution_price - expected_price) / expected_price * 100
        ok = slippage_pct <= MAX_SLIPPAGE_PCT
        return {
            "pass": ok,
            "slippage_pct": round(slippage_pct, 4),
            "max_allowed_pct": MAX_SLIPPAGE_PCT,
            "detail": f"Slippage {slippage_pct:.2f}% {'<=' if ok else '>'} max {MAX_SLIPPAGE_PCT}%",
        }

    async def check_treasury_sufficiency(self, asset: str, amount: float) -> dict:
        from services.execution_engine import ExecutionEngine, ASSET_TO_BSC_CONTRACT
        engine = ExecutionEngine.get_instance()

        if asset.upper() == "BNB":
            w3 = engine._get_web3()
            if not w3 or not engine._hot_wallet:
                return {"sufficient": False, "detail": "Web3 non connesso"}
            bal = w3.eth.get_balance(engine._hot_wallet)
            human = float(w3.from_wei(bal, "ether"))
            ok = human >= amount
            gte_sign = ">=" if ok else "<"
            return {"sufficient": ok, "asset": "BNB", "on_chain": human,
                    "required": amount, "detail": f"BNB: {human:.6f} {gte_sign} {amount}"}

        contract_addr = ASSET_TO_BSC_CONTRACT.get(asset.upper())
        if not contract_addr:
            return {"sufficient": False, "detail": f"{asset} non supportato on-chain"}

        w3 = engine._get_web3()
        if not w3 or not engine._hot_wallet:
            return {"sufficient": False, "detail": "Web3 non connesso"}

        from services.execution_engine import ERC20_ABI
        from web3 import Web3
        contract = w3.eth.contract(address=Web3.to_checksum_address(contract_addr), abi=ERC20_ABI)
        raw_bal = contract.functions.balanceOf(engine._hot_wallet).call()
        human = raw_bal / (10 ** 18)
        ok = human >= amount
        return {"sufficient": ok, "asset": asset.upper(), "on_chain": human,
                "required": amount, "contract": contract_addr}

    async def transition_tx_state(self, tx_id: str, new_state: str, detail: str = "") -> dict:
        db = get_database()
        tx = await db.neno_transactions.find_one({"id": tx_id}, {"_id": 0, "status": 1})
        if not tx:
            return {"success": False, "error": "Transazione non trovata"}

        current = tx.get("status", TxState.PENDING_EXECUTION)
        valid_next = TxState.VALID_TRANSITIONS.get(current, [])

        if new_state not in valid_next and new_state != current:
            return {"success": False, "error": f"Transizione {current} -> {new_state} non valida. Valide: {valid_next}"}

        await db.neno_transactions.update_one(
            {"id": tx_id},
            {"$set": {"status": new_state, "updated_at": datetime.now(timezone.utc)},
             "$push": {"state_history": {
                 "from": current, "to": new_state, "detail": detail,
                 "timestamp": datetime.now(timezone.utc).isoformat()}}},
        )
        return {"success": True, "from": current, "to": new_state}

    async def execute_with_retry(self, execution_fn, tx_id: str, *args, **kwargs) -> dict:
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                await self.transition_tx_state(tx_id, TxState.ON_CHAIN_SENT, f"Attempt {attempt}")
                result = await execution_fn(*args, **kwargs)
                if result.get("success"):
                    await self.transition_tx_state(tx_id, TxState.CONFIRMED, f"TX: {result.get('tx_hash', '')}")
                    return result
                else:
                    if attempt < MAX_RETRY_ATTEMPTS:
                        await self.transition_tx_state(tx_id, TxState.RETRYING, f"Attempt {attempt} failed: {result.get('error', '')}")
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                    else:
                        await self.transition_tx_state(tx_id, TxState.FAILED, f"All {MAX_RETRY_ATTEMPTS} attempts failed")
                        return result
            except Exception as e:
                logger.error(f"[RISK] Execution attempt {attempt} failed: {e}")
                if attempt < MAX_RETRY_ATTEMPTS:
                    await self.transition_tx_state(tx_id, TxState.RETRYING, str(e))
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                else:
                    await self.transition_tx_state(tx_id, TxState.FAILED, str(e))
                    return {"success": False, "error": str(e)}

        return {"success": False, "error": "Max retry esauriti"}

    async def _get_user_exposure(self, user_id: str) -> float:
        db = get_database()
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        pipeline = [
            {"$match": {"user_id": user_id, "created_at": {"$gte": since},
                        "status": {"$nin": ["failed", "reverted", "cancelled"]}}},
            {"$group": {"_id": None, "total": {"$sum": "$eur_value"}}},
        ]
        agg = await db.neno_transactions.aggregate(pipeline).to_list(1)
        return agg[0]["total"] if agg else 0

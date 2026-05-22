"""
Audit Logger Service for PoR Engine.

Provides comprehensive audit logging for:
- Transaction lifecycle events
- Settlement processing traces
- Compliance status changes
- System health monitoring

All logs are structured JSON for easy parsing and analysis.
"""

import os
import logging
import json
from typing import Dict, Optional, Any
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from enum import Enum

# Configure structured logging
logger = logging.getLogger("por.audit")


class AuditEventType(str, Enum):
    """Audit event types."""
    # Transaction lifecycle
    QUOTE_CREATED = "quote.created"
    QUOTE_ACCEPTED = "quote.accepted"
    QUOTE_EXPIRED = "quote.expired"
    QUOTE_CANCELLED = "quote.cancelled"
    
    # Deposit events
    DEPOSIT_PENDING = "deposit.pending"
    DEPOSIT_DETECTED = "deposit.detected"
    DEPOSIT_CONFIRMED = "deposit.confirmed"
    DEPOSIT_FAILED = "deposit.failed"
    
    # Settlement events
    SETTLEMENT_INITIATED = "settlement.initiated"
    SETTLEMENT_PROCESSING = "settlement.processing"
    SETTLEMENT_COMPLETED = "settlement.completed"
    SETTLEMENT_FAILED = "settlement.failed"
    
    # Payout events
    PAYOUT_INITIATED = "payout.initiated"
    PAYOUT_COMPLETED = "payout.completed"
    PAYOUT_FAILED = "payout.failed"
    
    # Compliance events
    KYC_STATUS_CHANGE = "compliance.kyc_status_change"
    AML_STATUS_CHANGE = "compliance.aml_status_change"
    RISK_ASSESSMENT = "compliance.risk_assessment"
    
    # System events
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    RATE_LIMIT_HIT = "system.rate_limit"


class AuditLogger:
    """
    Structured audit logger for PoR engine.
    
    Logs to both console (structured JSON) and MongoDB for persistence.
    """
    
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        self.db = db
        self.audit_collection = db.audit_logs if db is not None else None
        self._enabled = True
        self._log_to_db = db is not None
    
    async def initialize(self):
        """Initialize audit logger."""
        if self.audit_collection is not None:
            await self.audit_collection.create_index("timestamp")
            await self.audit_collection.create_index("event_type")
            await self.audit_collection.create_index("quote_id")
            await self.audit_collection.create_index("settlement_id")
            logger.info("Audit logger initialized with MongoDB persistence")
        else:
            logger.info("Audit logger initialized (console only)")
    
    def _format_log(self, event_type: AuditEventType, data: Dict) -> str:
        """Format log entry as structured JSON."""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type.value,
            "service": "por_engine",
            **data
        }
        return json.dumps(log_entry)
    
    async def log(
        self,
        event_type: AuditEventType,
        quote_id: Optional[str] = None,
        settlement_id: Optional[str] = None,
        user_id: Optional[str] = None,
        api_key_id: Optional[str] = None,
        details: Optional[Dict] = None,
        error: Optional[str] = None
    ):
        """Log an audit event."""
        if not self._enabled:
            return
        
        data = {
            "quote_id": quote_id,
            "settlement_id": settlement_id,
            "user_id": user_id,
            "api_key_id": api_key_id,
            "details": details or {},
            "error": error
        }
        
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}
        
        # Log to console (structured JSON)
        log_message = self._format_log(event_type, data)
        
        if error:
            logger.error(log_message)
        else:
            logger.info(log_message)
        
        # Log to MongoDB if enabled
        if self._log_to_db and self.audit_collection is not None:
            try:
                doc = {
                    "timestamp": datetime.now(timezone.utc),
                    "event_type": event_type.value,
                    **data
                }
                await self.audit_collection.insert_one(doc)
            except Exception as e:
                logger.error(f"Failed to persist audit log: {e}")
    
    async def log_transaction_event(
        self,
        event_type: AuditEventType,
        quote_id: str,
        state: str,
        crypto_amount: Optional[float] = None,
        crypto_currency: Optional[str] = None,
        fiat_amount: Optional[float] = None,
        details: Optional[Dict] = None
    ):
        """Log a transaction lifecycle event."""
        await self.log(
            event_type=event_type,
            quote_id=quote_id,
            details={
                "state": state,
                "crypto_amount": crypto_amount,
                "crypto_currency": crypto_currency,
                "fiat_amount": fiat_amount,
                **(details or {})
            }
        )
    
    async def log_settlement_event(
        self,
        event_type: AuditEventType,
        quote_id: str,
        settlement_id: str,
        amount_eur: float,
        payout_reference: Optional[str] = None,
        bank_account: Optional[str] = None,
        details: Optional[Dict] = None
    ):
        """Log a settlement processing event."""
        await self.log(
            event_type=event_type,
            quote_id=quote_id,
            settlement_id=settlement_id,
            details={
                "amount_eur": amount_eur,
                "payout_reference": payout_reference,
                "bank_account_masked": bank_account[:8] + "..." if bank_account else None,
                **(details or {})
            }
        )
    
    async def log_compliance_event(
        self,
        event_type: AuditEventType,
        quote_id: str,
        status_field: str,
        old_status: Optional[str] = None,
        new_status: str = None,
        provider: str = "internal_por",
        details: Optional[Dict] = None
    ):
        """Log a compliance status change."""
        await self.log(
            event_type=event_type,
            quote_id=quote_id,
            details={
                "status_field": status_field,
                "old_status": old_status,
                "new_status": new_status,
                "provider": provider,
                **(details or {})
            }
        )
    
    async def log_system_event(
        self,
        event_type: AuditEventType,
        component: str,
        message: str,
        details: Optional[Dict] = None,
        error: Optional[str] = None
    ):
        """Log a system event."""
        await self.log(
            event_type=event_type,
            details={
                "component": component,
                "message": message,
                **(details or {})
            },
            error=error
        )
    
    async def get_audit_trail(self, quote_id: str) -> list:
        """Get complete audit trail for a quote."""
        if self.audit_collection is None:
            return []
        
        cursor = self.audit_collection.find(
            {"quote_id": quote_id}
        ).sort("timestamp", 1)
        
        docs = await cursor.to_list(length=1000)
        for doc in docs:
            doc.pop("_id", None)
            doc["timestamp"] = doc["timestamp"].isoformat() if hasattr(doc["timestamp"], "isoformat") else str(doc["timestamp"])
        
        return docs
    
    async def get_recent_events(
        self,
        event_type: Optional[AuditEventType] = None,
        limit: int = 100
    ) -> list:
        """Get recent audit events."""
        if self.audit_collection is None:
            return []
        
        query = {}
        if event_type:
            query["event_type"] = event_type.value
        
        cursor = self.audit_collection.find(query).sort("timestamp", -1).limit(limit)
        
        docs = await cursor.to_list(length=limit)
        for doc in docs:
            doc.pop("_id", None)
            doc["timestamp"] = doc["timestamp"].isoformat() if hasattr(doc["timestamp"], "isoformat") else str(doc["timestamp"])
        
        return docs


# Global audit logger instance
audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global audit_logger
    if audit_logger is None:
        audit_logger = AuditLogger()
    return audit_logger


def set_audit_logger(logger: AuditLogger):
    """Set the global audit logger instance."""
    global audit_logger
    audit_logger = logger



# ────────────────────────────────────────────────────────────
#  AGGRESSIVE TRADE AUDIT — Sell/Swap/Off-Ramp
# ────────────────────────────────────────────────────────────

import uuid as _uuid
from decimal import Decimal as _Decimal
from database.mongodb import get_database as _get_db

_agg_logger = logging.getLogger("audit.aggressive")
_agg_logger.setLevel(logging.INFO)

NENO_CONTRACT = "0xeF3F5C1892A8d7A3304E4A15959E124402d69974"
_TREASURY_USER_ID = os.environ.get("TREASURY_USER_ID", "")


async def _read_onchain_neno(wallet_address: str) -> float:
    try:
        from services.execution_engine import ExecutionEngine, ERC20_ABI
        from web3 import Web3
        engine = ExecutionEngine.get_instance()
        w3 = engine._get_web3()
        if not w3:
            return -1
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(NENO_CONTRACT), abi=ERC20_ABI
        )
        raw = contract.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
        return float(_Decimal(raw) / _Decimal(10 ** 18))
    except Exception as e:
        _agg_logger.warning(f"[AUDIT] On-chain NENO read failed: {e}")
        return -1


async def _read_onchain_bnb(wallet_address: str) -> float:
    try:
        from services.execution_engine import ExecutionEngine
        from web3 import Web3
        engine = ExecutionEngine.get_instance()
        w3 = engine._get_web3()
        if not w3:
            return -1
        raw = w3.eth.get_balance(Web3.to_checksum_address(wallet_address))
        return float(_Decimal(raw) / _Decimal(10 ** 18))
    except Exception as e:
        _agg_logger.warning(f"[AUDIT] On-chain BNB read failed: {e}")
        return -1


async def log_pre_operation(
    op_type: str, user_id: str, user_email: str,
    assets_involved: list, neno_amount: float = 0,
    extra: dict = None
) -> dict:
    """PRE-OPERATION audit snapshot: balances, on-chain state, timestamp."""
    db = _get_db()
    ts = datetime.now(timezone.utc)
    snapshot = {
        "timestamp": ts.isoformat(),
        "timestamp_unix": ts.timestamp(),
        "operation": op_type,
        "user_id": user_id,
        "user_email": user_email,
        "neno_amount": neno_amount,
        "balances_pre": {},
        "treasury_pre": {},
        "onchain_pre": {},
    }

    for asset in assets_involved:
        w = await db.wallets.find_one({"user_id": user_id, "asset": asset.upper()}, {"_id": 0})
        snapshot["balances_pre"][asset] = round(w.get("balance", 0), 8) if w else 0

    if _TREASURY_USER_ID:
        for asset in assets_involved:
            w = await db.wallets.find_one({"user_id": _TREASURY_USER_ID, "asset": asset.upper()}, {"_id": 0})
            snapshot["treasury_pre"][asset] = round(w.get("balance", 0), 8) if w else 0

    try:
        from services.execution_engine import ExecutionEngine
        engine = ExecutionEngine.get_instance()
        if engine.hot_wallet:
            snapshot["onchain_pre"] = {
                "hot_wallet": engine.hot_wallet,
                "NENO": round(await _read_onchain_neno(engine.hot_wallet), 8),
                "BNB": round(await _read_onchain_bnb(engine.hot_wallet), 8),
            }
    except Exception:
        pass

    if extra:
        snapshot["extra"] = extra

    _agg_logger.info(
        f"[AUDIT PRE] {op_type} | user={user_email} | ts={ts.isoformat()} | "
        f"user_bal={snapshot['balances_pre']} | treasury_bal={snapshot['treasury_pre']} | "
        f"onchain={snapshot['onchain_pre']}"
    )
    return snapshot


async def log_post_operation(
    pre_snapshot: dict, result: dict,
    assets_involved: list, tx_id: str = "",
    error: str = None
) -> dict:
    """POST-OPERATION audit: deltas, consistency check, persist to DB."""
    db = _get_db()
    ts = datetime.now(timezone.utc)
    user_id = pre_snapshot["user_id"]
    op_type = pre_snapshot["operation"]

    post = {
        "timestamp": ts.isoformat(),
        "timestamp_unix": ts.timestamp(),
        "duration_ms": round((ts.timestamp() - pre_snapshot["timestamp_unix"]) * 1000, 1),
        "tx_id": tx_id, "operation": op_type,
        "user_id": user_id, "user_email": pre_snapshot.get("user_email", ""),
        "error": error,
        "balances_post": {}, "treasury_post": {}, "onchain_post": {},
        "deltas_user": {}, "deltas_treasury": {}, "deltas_onchain": {},
        "consistency_ok": True, "consistency_issues": [],
    }

    for asset in assets_involved:
        w = await db.wallets.find_one({"user_id": user_id, "asset": asset.upper()}, {"_id": 0})
        bal = round(w.get("balance", 0), 8) if w else 0
        post["balances_post"][asset] = bal
        post["deltas_user"][asset] = round(bal - pre_snapshot["balances_pre"].get(asset, 0), 8)

    if _TREASURY_USER_ID:
        for asset in assets_involved:
            w = await db.wallets.find_one({"user_id": _TREASURY_USER_ID, "asset": asset.upper()}, {"_id": 0})
            bal = round(w.get("balance", 0), 8) if w else 0
            post["treasury_post"][asset] = bal
            post["deltas_treasury"][asset] = round(bal - pre_snapshot["treasury_pre"].get(asset, 0), 8)

    try:
        from services.execution_engine import ExecutionEngine
        engine = ExecutionEngine.get_instance()
        if engine.hot_wallet:
            neno_oc = await _read_onchain_neno(engine.hot_wallet)
            bnb_oc = await _read_onchain_bnb(engine.hot_wallet)
            post["onchain_post"] = {"NENO": round(neno_oc, 8), "BNB": round(bnb_oc, 8)}
            pre_neno = pre_snapshot.get("onchain_pre", {}).get("NENO", 0)
            pre_bnb = pre_snapshot.get("onchain_pre", {}).get("BNB", 0)
            post["deltas_onchain"] = {
                "NENO": round(neno_oc - pre_neno, 8) if pre_neno >= 0 else 0,
                "BNB": round(bnb_oc - pre_bnb, 8) if pre_bnb >= 0 else 0,
            }
    except Exception:
        pass

    for asset in assets_involved:
        ud = post["deltas_user"].get(asset, 0)
        td = post["deltas_treasury"].get(asset, 0)
        if abs(ud + td) > 0.01 and not error and asset in ("NENO", "EUR", "ETH", "BTC"):
            issue = f"MISMATCH {asset}: user={ud:+.8f} treasury={td:+.8f} net={ud + td:+.8f}"
            post["consistency_issues"].append(issue)
            post["consistency_ok"] = False

    await db.audit_aggressive_log.insert_one({
        "_id": tx_id or f"audit_{ts.timestamp()}",
        "pre": pre_snapshot, "post": post,
        "result_summary": {
            "status": "error" if error else "success",
            "message": result.get("message", "") if isinstance(result, dict) else str(result),
        },
        "created_at": ts.isoformat(),
    })

    status = "ERROR" if error else ("WARN" if not post["consistency_ok"] else "OK")
    _agg_logger.info(
        f"[AUDIT POST] {op_type} | {status} | tx={tx_id[:12]}... | "
        f"duration={post['duration_ms']}ms | "
        f"user_deltas={post['deltas_user']} | "
        f"treasury_deltas={post['deltas_treasury']} | "
        f"onchain_deltas={post['deltas_onchain']} | "
        f"consistency={'OK' if post['consistency_ok'] else 'FAIL: ' + str(post['consistency_issues'])}"
    )

    if not post["consistency_ok"]:
        _agg_logger.error(f"[AUDIT ALERT] CONSISTENCY FAILURE tx={tx_id}: {post['consistency_issues']}")

    return post

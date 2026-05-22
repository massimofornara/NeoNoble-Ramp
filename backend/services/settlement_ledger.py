"""
Settlement Ledger — NeoNoble Ramp.

Production-grade transaction state machine, payout queue, and reconciliation engine.
States: on_chain_executed → internal_credited → payout_pending → payout_sent → payout_settled
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from database.mongodb import get_database

logger = logging.getLogger(__name__)

# Transaction states
STATE_ONCHAIN_EXECUTED = "on_chain_executed"
STATE_INTERNAL_CREDITED = "internal_credited"
STATE_PAYOUT_PENDING = "payout_pending"
STATE_PAYOUT_SENT = "payout_sent"
STATE_PAYOUT_SETTLED = "payout_settled"
STATE_PAYOUT_FAILED = "payout_failed"
STATE_PAYOUT_EXECUTED_EXTERNAL = "payout_executed_external"

VALID_TRANSITIONS = {
    STATE_ONCHAIN_EXECUTED: [STATE_INTERNAL_CREDITED],
    STATE_INTERNAL_CREDITED: [STATE_PAYOUT_PENDING, STATE_PAYOUT_EXECUTED_EXTERNAL],
    STATE_PAYOUT_PENDING: [STATE_PAYOUT_SENT, STATE_PAYOUT_FAILED, STATE_PAYOUT_EXECUTED_EXTERNAL],
    STATE_PAYOUT_SENT: [STATE_PAYOUT_SETTLED, STATE_PAYOUT_FAILED],
    STATE_PAYOUT_FAILED: [STATE_PAYOUT_PENDING],
    STATE_PAYOUT_EXECUTED_EXTERNAL: [],
}


async def create_ledger_entry(
    user_id: str,
    tx_type: str,
    debit_asset: str,
    debit_amount: float,
    credit_asset: str,
    credit_amount: float,
    fee_amount: float = 0,
    fee_asset: str = "EUR",
    onchain_tx_hash: Optional[str] = None,
    destination_type: Optional[str] = None,
    destination_details: Optional[dict] = None,
    initial_state: str = STATE_INTERNAL_CREDITED,
) -> dict:
    """Create a ledger entry with full audit trail."""
    db = get_database()
    entry_id = str(uuid.uuid4())

    entry = {
        "id": entry_id,
        "user_id": user_id,
        "type": tx_type,
        "debit_asset": debit_asset,
        "debit_amount": round(debit_amount, 8),
        "credit_asset": credit_asset,
        "credit_amount": round(credit_amount, 8),
        "fee_amount": round(fee_amount, 8),
        "fee_asset": fee_asset,
        "state": initial_state,
        "onchain_tx_hash": onchain_tx_hash,
        "destination_type": destination_type,
        "destination_details": destination_details or {},
        "state_history": [
            {"state": initial_state, "at": datetime.now(timezone.utc).isoformat(), "note": "created"}
        ],
        "retry_count": 0,
        "max_retries": 3,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.settlement_ledger.insert_one({**entry, "_id": entry_id})
    logger.info(f"[LEDGER] Created entry {entry_id}: {tx_type} {debit_amount} {debit_asset} → {credit_amount} {credit_asset} [{initial_state}]")
    return entry


async def transition_state(entry_id: str, new_state: str, note: str = "") -> bool:
    """Transition a ledger entry to a new state with validation."""
    db = get_database()
    entry = await db.settlement_ledger.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        logger.error(f"[LEDGER] Entry {entry_id} not found")
        return False

    current_state = entry["state"]
    allowed = VALID_TRANSITIONS.get(current_state, [])
    if new_state not in allowed:
        logger.error(f"[LEDGER] Invalid transition {current_state} → {new_state} for {entry_id}")
        return False

    state_entry = {"state": new_state, "at": datetime.now(timezone.utc).isoformat(), "note": note}

    await db.settlement_ledger.update_one(
        {"id": entry_id},
        {
            "$set": {"state": new_state, "updated_at": datetime.now(timezone.utc).isoformat()},
            "$push": {"state_history": state_entry},
        },
    )
    logger.info(f"[LEDGER] {entry_id}: {current_state} → {new_state} ({note})")
    return True


async def enqueue_payout(
    user_id: str,
    amount: float,
    currency: str,
    destination_type: str,
    destination_iban: Optional[str] = None,
    destination_card_id: Optional[str] = None,
    beneficiary_name: Optional[str] = None,
    ledger_entry_id: Optional[str] = None,
) -> dict:
    """Create a payout queue entry for off-ramp processing."""
    db = get_database()
    payout_id = str(uuid.uuid4())

    payout = {
        "id": payout_id,
        "user_id": user_id,
        "amount": round(amount, 2),
        "currency": currency,
        "destination_type": destination_type,
        "destination_iban": destination_iban,
        "destination_card_id": destination_card_id,
        "beneficiary_name": beneficiary_name,
        "ledger_entry_id": ledger_entry_id,
        "state": STATE_PAYOUT_PENDING,
        "provider": None,
        "provider_ref": None,
        "retry_count": 0,
        "max_retries": 3,
        "error_log": [],
        "state_history": [
            {"state": STATE_PAYOUT_PENDING, "at": datetime.now(timezone.utc).isoformat(), "note": "queued"}
        ],
        "webhook_url": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.payout_queue.insert_one({**payout, "_id": payout_id})
    logger.info(f"[PAYOUT] Queued payout {payout_id}: {amount} {currency} → {destination_type} ({destination_iban or destination_card_id})")
    return payout


async def process_payout_queue():
    """Process pending payouts. Called by background scheduler.
    When NIUM/banking provider is configured, this executes real transfers.
    Without provider: marks as payout_pending, ready for manual processing or API key activation."""
    db = get_database()
    import os

    nium_key = os.environ.get("NIUM_API_KEY")
    has_provider = bool(nium_key)

    pending = await db.payout_queue.find(
        {"state": STATE_PAYOUT_PENDING, "retry_count": {"$lt": 3}}
    ).to_list(50)

    for payout in pending:
        pid = payout["id"]
        if has_provider:
            success = await _execute_nium_payout(payout)
            if success:
                await _update_payout_state(db, pid, STATE_PAYOUT_SENT, "Sent via NIUM")
                if payout.get("ledger_entry_id"):
                    await transition_state(payout["ledger_entry_id"], STATE_PAYOUT_SENT, "NIUM transfer initiated")
            else:
                await db.payout_queue.update_one(
                    {"id": pid},
                    {
                        "$inc": {"retry_count": 1},
                        "$push": {"error_log": {"at": datetime.now(timezone.utc).isoformat(), "error": "NIUM call failed"}},
                    },
                )
        else:
            logger.debug(f"[PAYOUT] {pid} waiting for banking provider activation")


async def _execute_nium_payout(payout: dict) -> bool:
    """Execute a real payout via NIUM. Returns True on success."""
    import os
    import httpx

    nium_key = os.environ.get("NIUM_API_KEY")
    nium_url = os.environ.get("NIUM_BASE_URL", "https://gateway.nium.com")
    client_id = os.environ.get("NIUM_CLIENT_ID", "")

    if not nium_key:
        return False

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{nium_url}/api/v1/client/{client_id}/transactions/transfermoney",
                headers={
                    "x-api-key": nium_key,
                    "Content-Type": "application/json",
                },
                json={
                    "beneficiary": {
                        "name": payout.get("beneficiary_name", ""),
                        "accountNumber": payout.get("destination_iban", ""),
                    },
                    "amount": payout["amount"],
                    "currency": payout["currency"],
                    "purpose": "NENO Off-Ramp Payout",
                },
            )
            if resp.status_code < 300:
                ref = resp.json().get("systemReferenceNumber", "")
                db = get_database()
                await db.payout_queue.update_one(
                    {"id": payout["id"]},
                    {"$set": {"provider": "NIUM", "provider_ref": ref}},
                )
                return True
            else:
                logger.error(f"[PAYOUT] NIUM error {resp.status_code}: {resp.text[:200]}")
                return False
    except Exception as e:
        logger.error(f"[PAYOUT] NIUM exception: {e}")
        return False


async def _update_payout_state(db, payout_id: str, new_state: str, note: str):
    """Update payout queue state."""
    await db.payout_queue.update_one(
        {"id": payout_id},
        {
            "$set": {"state": new_state, "updated_at": datetime.now(timezone.utc).isoformat()},
            "$push": {"state_history": {"state": new_state, "at": datetime.now(timezone.utc).isoformat(), "note": note}},
        },
    )


async def get_user_ledger(user_id: str, limit: int = 50) -> list:
    """Get ledger entries for a user."""
    db = get_database()
    entries = await db.settlement_ledger.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(limit)
    return entries


async def get_user_payouts(user_id: str, limit: int = 50) -> list:
    """Get payout queue entries for a user."""
    db = get_database()
    payouts = await db.payout_queue.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(limit)
    return payouts


async def reconcile_deposits():
    """Reconciliation: find all unmatched on-chain deposits and credit them."""
    db = get_database()
    unmatched = await db.onchain_deposits.find(
        {"credited": False, "user_id": {"$ne": None}}
    ).to_list(100)

    credited_count = 0
    for dep in unmatched:
        uid = dep["user_id"]
        amount = dep["neno_amount"]
        tx_hash = dep["tx_hash"]

        wallet = await db.wallets.find_one({"user_id": uid, "asset": "NENO"})
        if wallet:
            await db.wallets.update_one({"user_id": uid, "asset": "NENO"}, {"$inc": {"balance": amount}})
        else:
            await db.wallets.insert_one({
                "id": str(uuid.uuid4()), "user_id": uid, "asset": "NENO",
                "balance": amount, "created_at": datetime.now(timezone.utc),
            })

        await db.onchain_deposits.update_one({"tx_hash": tx_hash}, {"$set": {"credited": True}})
        credited_count += 1
        logger.info(f"[RECONCILE] Credited {amount} NENO to {uid} (tx: {tx_hash[:16]}...)")

    return credited_count

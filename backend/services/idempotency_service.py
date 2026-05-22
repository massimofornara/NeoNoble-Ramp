"""
Idempotency Service — NeoNoble Ramp.

Prevents duplicate financial operations (E11000) via:
- Pre-check before DB insert
- Idempotency key deduplication
- Safe upsert for transaction logging
"""

import logging
import hashlib
from datetime import datetime, timezone, timedelta

from database.mongodb import get_database

logger = logging.getLogger("idempotency")

# TTL for idempotency keys (24 hours)
IDEMPOTENCY_TTL_HOURS = 24


class IdempotencyService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def generate_key(user_id: str, op_type: str, **kwargs) -> str:
        """Generate a deterministic idempotency key from operation parameters."""
        raw = f"{user_id}:{op_type}"
        for k in sorted(kwargs.keys()):
            raw += f":{k}={kwargs[k]}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def check_and_lock(self, idempotency_key: str, op_type: str, user_id: str) -> dict:
        """
        Check if an operation with this key already exists.
        If not, create a lock. Returns {"locked": True} if new, or {"locked": False, "existing": ...} if duplicate.
        """
        db = get_database()
        now = datetime.now(timezone.utc)

        existing = await db.idempotency_keys.find_one({"_id": idempotency_key}, {"_id": 0})
        if existing:
            logger.warning(f"[IDEMPOTENCY] Duplicate detected: {op_type} for user {user_id} key={idempotency_key[:16]}...")
            return {"locked": False, "existing": existing}

        try:
            await db.idempotency_keys.insert_one({
                "_id": idempotency_key,
                "op_type": op_type,
                "user_id": user_id,
                "status": "processing",
                "created_at": now,
                "expires_at": now + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
            })
            return {"locked": True}
        except Exception:
            # Race condition: another request just inserted
            existing = await db.idempotency_keys.find_one({"_id": idempotency_key}, {"_id": 0})
            return {"locked": False, "existing": existing or {}}

    async def mark_completed(self, idempotency_key: str, tx_id: str, result_summary: dict):
        """Mark an idempotency key as completed with the transaction result."""
        db = get_database()
        await db.idempotency_keys.update_one(
            {"_id": idempotency_key},
            {"$set": {
                "status": "completed",
                "tx_id": tx_id,
                "result_summary": result_summary,
                "completed_at": datetime.now(timezone.utc),
            }},
        )

    async def mark_failed(self, idempotency_key: str, error: str):
        """Mark as failed so it can be retried."""
        db = get_database()
        await db.idempotency_keys.update_one(
            {"_id": idempotency_key},
            {"$set": {"status": "failed", "error": error, "failed_at": datetime.now(timezone.utc)}},
        )

    async def cleanup_expired(self):
        """Remove expired idempotency keys."""
        db = get_database()
        now = datetime.now(timezone.utc)
        result = await db.idempotency_keys.delete_many({"expires_at": {"$lt": now}})
        if result.deleted_count > 0:
            logger.info(f"[IDEMPOTENCY] Cleaned {result.deleted_count} expired keys")

    async def ensure_indexes(self):
        """Create TTL and compound indexes for the idempotency collection."""
        db = get_database()
        try:
            await db.idempotency_keys.create_index("expires_at", expireAfterSeconds=0)
            await db.idempotency_keys.create_index([("user_id", 1), ("op_type", 1)])
            logger.info("[IDEMPOTENCY] Indexes created")
        except Exception as e:
            logger.warning(f"[IDEMPOTENCY] Index creation warning: {e}")


async def safe_log_tx(db, tx: dict):
    """
    Safe transaction logging that prevents E11000 duplicate key errors.
    Uses update_one with upsert instead of insert_one.
    """
    doc = {**tx}
    tx_id = doc.get("id", "")
    if not tx_id:
        return
    # Remove _id if present to avoid conflict
    doc.pop("_id", None)
    try:
        await db.neno_transactions.update_one(
            {"_id": tx_id},
            {"$setOnInsert": doc},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"[SAFE_LOG] Transaction log error for {tx_id}: {e}")

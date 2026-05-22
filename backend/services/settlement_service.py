"""
Settlement Service for off-ramp payout routing.

Handles:
- Payout routing (SEPA, Wire, Instant)
- Settlement batch processing
- Provider fee reconciliation
- Settlement lifecycle management
"""

import os
import logging
from typing import Dict, Optional, List, Tuple
from datetime import datetime, timezone
from uuid import uuid4
from motor.motor_asyncio import AsyncIOMotorDatabase

from services.provider_interface import (
    SettlementMode,
    TransactionState,
    SettlementResult
)

logger = logging.getLogger(__name__)


class SettlementService:
    """
    Settlement service for managing payout routing and settlement.
    
    Supports multiple settlement modes:
    - INSTANT: Immediate settlement
    - SIMULATED_DELAY: Realistic banking delays
    - BATCH: Scheduled batch processing
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.settlements_collection = db.settlements
        self.batches_collection = db.settlement_batches
        self._mode = SettlementMode.INSTANT
        self._initialized = False
    
    async def initialize(self):
        """Initialize the settlement service."""
        if self._initialized:
            return
        
        await self.settlements_collection.create_index("settlement_id", unique=True, sparse=True)
        await self.settlements_collection.create_index("quote_id")
        await self.settlements_collection.create_index("status")
        await self.settlements_collection.create_index("created_at")
        
        await self.batches_collection.create_index("batch_id", unique=True)
        await self.batches_collection.create_index("status")
        
        self._initialized = True
        logger.info(f"Settlement service initialized (mode: {self._mode.value})")
    
    def set_mode(self, mode: SettlementMode):
        """Set settlement mode."""
        self._mode = mode
        logger.info(f"Settlement mode changed to: {mode.value}")
    
    def get_mode(self) -> SettlementMode:
        """Get current settlement mode."""
        return self._mode
    
    async def create_settlement(
        self,
        quote_id: str,
        amount_eur: float,
        fee_eur: float,
        bank_account: str,
        beneficiary_name: Optional[str] = None
    ) -> Tuple[Optional[SettlementResult], Optional[str]]:
        """
        Create a new settlement record.
        """
        try:
            await self.initialize()
            
            settlement_id = f"stl_{uuid4().hex[:12]}"
            payout_ref = f"PAY-{quote_id[-8:].upper()}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            now = datetime.now(timezone.utc)
            
            # Determine initial status based on mode
            status = "processing"
            
            settlement_doc = {
                "settlement_id": settlement_id,
                "quote_id": quote_id,
                "amount_eur": amount_eur,
                "fee_eur": fee_eur,
                "net_payout_eur": amount_eur - fee_eur,
                "payout_reference": payout_ref,
                "bank_account": bank_account,
                "beneficiary_name": beneficiary_name,
                "payout_method": "SEPA",
                "status": status,
                "mode": self._mode.value,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "completed_at": now.isoformat() if status == "completed" else None,
                "batch_id": None
            }
            
            await self.settlements_collection.insert_one(settlement_doc)
            
            result = SettlementResult(
                success=True,
                settlement_id=settlement_id,
                payout_reference=payout_ref,
                state=TransactionState.COMPLETED if status == "completed" else TransactionState.SETTLEMENT_PENDING,
                details={
                    "amount_eur": amount_eur,
                    "fee_eur": fee_eur,
                    "net_payout_eur": amount_eur - fee_eur,
                    "payout_method": "SEPA",
                    "status": status
                }
            )
            
            logger.info(f"Settlement created: {settlement_id} | €{amount_eur - fee_eur:,.2f} | {status}")
            
            return result, None
            
        except Exception as e:
            logger.error(f"Error creating settlement: {e}")
            return None, str(e)
    
    async def get_settlement(self, settlement_id: str) -> Optional[Dict]:
        """Get settlement by ID."""
        doc = await self.settlements_collection.find_one({"settlement_id": settlement_id})
        if doc:
            doc.pop("_id", None)
        return doc
    
    async def get_settlement_by_quote(self, quote_id: str) -> Optional[Dict]:
        """Get settlement by quote ID."""
        doc = await self.settlements_collection.find_one({"quote_id": quote_id})
        if doc:
            doc.pop("_id", None)
        return doc
    
    async def update_settlement_status(
        self,
        settlement_id: str,
        status: str,
        details: Optional[Dict] = None
    ) -> bool:
        """Update settlement status."""
        update_doc = {
            "status": status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if status == "completed":
            update_doc["completed_at"] = datetime.now(timezone.utc).isoformat()
        
        if details:
            update_doc.update(details)
        
        result = await self.settlements_collection.update_one(
            {"settlement_id": settlement_id},
            {"$set": update_doc}
        )
        
        return result.modified_count > 0
    
    async def list_pending_settlements(self, limit: int = 100) -> List[Dict]:
        """List all pending settlements."""
        cursor = self.settlements_collection.find(
            {"status": "pending"}
        ).sort("created_at", 1).limit(limit)
        
        docs = await cursor.to_list(length=limit)
        for doc in docs:
            doc.pop("_id", None)
        return docs
    
    async def process_batch(self) -> Dict:
        """
        Process pending settlements in batch.
        Used when settlement_mode is BATCH.
        """
        pending = await self.list_pending_settlements()
        
        if not pending:
            return {"processed": 0, "message": "No pending settlements"}
        
        batch_id = f"batch_{uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)
        processed = 0
        total_amount = 0.0
        
        for settlement in pending:
            # Update settlement
            await self.settlements_collection.update_one(
                {"settlement_id": settlement["settlement_id"]},
                {
                    "$set": {
                        "status": "completed",
                        "batch_id": batch_id,
                        "completed_at": now.isoformat(),
                        "updated_at": now.isoformat()
                    }
                }
            )
            processed += 1
            total_amount += settlement["net_payout_eur"]
        
        # Create batch record
        batch_doc = {
            "batch_id": batch_id,
            "settlement_count": processed,
            "total_amount_eur": total_amount,
            "status": "completed",
            "created_at": now.isoformat(),
            "completed_at": now.isoformat()
        }
        await self.batches_collection.insert_one(batch_doc)
        
        logger.info(f"Batch settlement processed: {batch_id} | {processed} settlements | €{total_amount:,.2f}")
        
        return {
            "batch_id": batch_id,
            "processed": processed,
            "total_amount_eur": total_amount
        }
    
    async def get_statistics(self) -> Dict:
        """Get settlement statistics."""
        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "total_eur": {"$sum": "$net_payout_eur"}
                }
            }
        ]
        
        results = await self.settlements_collection.aggregate(pipeline).to_list(length=10)
        
        stats = {
            "by_status": {r["_id"]: {"count": r["count"], "total_eur": r["total_eur"]} for r in results},
            "settlement_mode": self._mode.value
        }
        
        return stats

async def settle_transaction(self, quote_id: str, execution: Dict, payout: Dict):
    """
    REAL settlement after execution + payout.
    """
    try:
        await self.settlements_collection.update_one(
            {"quote_id": quote_id},
            {
                "$set": {
                    "status": "completed" if payout.get("success") else "failed",
                    "execution": execution,
                    "payout": payout,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )

        logger.info(f"Settlement completed for {quote_id}")

    except Exception as e:
        logger.error(f"Settlement failed: {e}")


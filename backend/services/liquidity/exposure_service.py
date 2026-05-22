"""
Exposure Service.

Manages treasury exposure tracking including:
- Per-transaction exposure records
- Exposure lifecycle management
- Coverage tracking
- Exposure aggregation and summaries

Each transaction generates an exposure record that must be reconciled.
"""

import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timezone
from uuid import uuid4
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.liquidity.exposure_models import (
    ExposureType,
    ExposureStatus,
    ExposureRecord,
    ExposureSummary
)

logger = logging.getLogger(__name__)


class ExposureService:
    """
    Exposure tracking service.
    
    Features:
    - Per-transaction exposure records
    - Reconstructable exposure history
    - Coverage tracking integration
    - Real-time exposure aggregation
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.exposure_collection = db.exposure_records
        self._initialized = False
    
    async def initialize(self):
        """Initialize exposure service."""
        if self._initialized:
            return
        
        # Create indexes
        await self.exposure_collection.create_index("exposure_id", unique=True)
        await self.exposure_collection.create_index("quote_id")
        await self.exposure_collection.create_index("status")
        await self.exposure_collection.create_index("created_at")
        await self.exposure_collection.create_index([("status", 1), ("created_at", -1)])
        
        self._initialized = True
        logger.info("Exposure Service initialized")
    
    async def create_exposure(
        self,
        quote_id: str,
        exposure_type: ExposureType,
        crypto_amount: float,
        crypto_currency: str,
        fiat_amount: float,
        fiat_currency: str = "EUR",
        exchange_rate: float = 0.0,
        direction: str = "offramp",
        deposit_tx_hash: Optional[str] = None,
        deposit_block: Optional[int] = None,
        payout_provider: Optional[str] = None,
        payout_reference: Optional[str] = None,
        treasury_snapshot_id: Optional[str] = None,
        treasury_coverage_ratio: float = 0.0
    ) -> ExposureRecord:
        """
        Create a new exposure record.
        
        Called when a payout is executed to track the resulting exposure.
        """
        now = datetime.now(timezone.utc)
        
        # Calculate exposure delta (EUR)
        # For off-ramp: we pay out fiat, creating negative exposure
        # The NENO received covers this exposure when converted
        exposure_delta = fiat_amount  # Positive = we owe this much coverage
        
        exposure = ExposureRecord(
            exposure_id=f"exp_{uuid4().hex[:12]}",
            exposure_type=exposure_type,
            status=ExposureStatus.CREATED,
            quote_id=quote_id,
            direction=direction,
            crypto_amount=crypto_amount,
            crypto_currency=crypto_currency,
            fiat_amount=fiat_amount,
            fiat_currency=fiat_currency,
            exposure_delta_eur=exposure_delta,
            exchange_rate=exchange_rate,
            rate_source="internal",
            deposit_tx_hash=deposit_tx_hash,
            deposit_block=deposit_block,
            payout_provider=payout_provider,
            payout_reference=payout_reference,
            treasury_snapshot_id=treasury_snapshot_id,
            treasury_coverage_ratio_at_creation=treasury_coverage_ratio,
            created_at=now.isoformat(),
            updated_at=now.isoformat()
        )
        
        # Store in database
        await self.exposure_collection.insert_one(exposure.to_dict())
        
        logger.info(
            f"Exposure Created: {exposure.exposure_id} | "
            f"Quote: {quote_id} | "
            f"Delta: €{exposure_delta:,.2f} | "
            f"Type: {exposure_type.value}"
        )
        
        return exposure
    
    async def update_exposure_status(
        self,
        exposure_id: str,
        status: ExposureStatus,
        settlement_id: Optional[str] = None
    ) -> Optional[ExposureRecord]:
        """Update exposure status."""
        now = datetime.now(timezone.utc)
        
        update = {
            "status": status.value,
            "updated_at": now.isoformat()
        }
        
        if settlement_id:
            update["settlement_id"] = settlement_id
        
        if status == ExposureStatus.SETTLED:
            update["settled_at"] = now.isoformat()
        
        result = await self.exposure_collection.find_one_and_update(
            {"exposure_id": exposure_id},
            {"$set": update},
            return_document=True
        )
        
        if result:
            logger.info(f"Exposure {exposure_id} status updated to {status.value}")
            return ExposureRecord(**{k: v for k, v in result.items() if k != "_id"})
        
        return None
    
    async def add_coverage(
        self,
        exposure_id: str,
        coverage_amount_eur: float,
        coverage_event_id: str
    ) -> Optional[ExposureRecord]:
        """Add coverage to an exposure record."""
        now = datetime.now(timezone.utc)
        
        # Get current exposure
        exposure_doc = await self.exposure_collection.find_one({"exposure_id": exposure_id})
        if not exposure_doc:
            return None
        
        current_covered = exposure_doc.get("covered_amount_eur", 0.0)
        exposure_delta = exposure_doc.get("exposure_delta_eur", 0.0)
        
        new_covered = current_covered + coverage_amount_eur
        coverage_pct = (new_covered / exposure_delta * 100) if exposure_delta > 0 else 100.0
        
        # Determine new status
        new_status = ExposureStatus.ACTIVE.value
        if coverage_pct >= 100:
            new_status = ExposureStatus.FULLY_COVERED.value
        elif coverage_pct > 0:
            new_status = ExposureStatus.PARTIALLY_COVERED.value
        
        result = await self.exposure_collection.find_one_and_update(
            {"exposure_id": exposure_id},
            {
                "$set": {
                    "covered_amount_eur": new_covered,
                    "coverage_percentage": min(coverage_pct, 100.0),
                    "status": new_status,
                    "updated_at": now.isoformat()
                },
                "$push": {"coverage_events": coverage_event_id}
            },
            return_document=True
        )
        
        if result:
            logger.info(
                f"Exposure {exposure_id} coverage added: €{coverage_amount_eur:,.2f} | "
                f"Total: {coverage_pct:.1f}%"
            )
        
        return result
    
    async def get_exposure(self, exposure_id: str) -> Optional[Dict]:
        """Get exposure by ID."""
        doc = await self.exposure_collection.find_one(
            {"exposure_id": exposure_id},
            {"_id": 0}
        )
        return doc
    
    async def get_exposure_by_quote(self, quote_id: str) -> Optional[Dict]:
        """Get exposure by quote ID."""
        doc = await self.exposure_collection.find_one(
            {"quote_id": quote_id},
            {"_id": 0}
        )
        return doc
    
    async def get_active_exposures(self, limit: int = 100) -> List[Dict]:
        """Get all active (uncovered) exposures."""
        cursor = self.exposure_collection.find(
            {"status": {"$in": [
                ExposureStatus.CREATED.value,
                ExposureStatus.ACTIVE.value,
                ExposureStatus.PARTIALLY_COVERED.value
            ]}},
            {"_id": 0}
        ).sort("created_at", -1).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def get_total_active_exposure(self) -> float:
        """Calculate total active exposure in EUR."""
        pipeline = [
            {
                "$match": {
                    "status": {"$in": [
                        ExposureStatus.CREATED.value,
                        ExposureStatus.ACTIVE.value,
                        ExposureStatus.PARTIALLY_COVERED.value
                    ]}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_exposure": {"$sum": "$exposure_delta_eur"},
                    "total_covered": {"$sum": "$covered_amount_eur"}
                }
            }
        ]
        
        results = await self.exposure_collection.aggregate(pipeline).to_list(length=1)
        
        if results:
            total = results[0].get("total_exposure", 0.0)
            covered = results[0].get("total_covered", 0.0)
            return total - covered
        
        return 0.0
    
    async def get_exposure_summary(self) -> ExposureSummary:
        """Generate exposure summary."""
        now = datetime.now(timezone.utc)
        
        # Aggregate by status
        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "total_eur": {"$sum": "$exposure_delta_eur"},
                    "total_covered": {"$sum": "$covered_amount_eur"}
                }
            }
        ]
        
        results = await self.exposure_collection.aggregate(pipeline).to_list(length=20)
        
        summary = ExposureSummary(timestamp=now.isoformat())
        
        for r in results:
            status = r["_id"]
            count = r["count"]
            total = r["total_eur"]
            covered = r["total_covered"]
            
            if status in [ExposureStatus.CREATED.value, ExposureStatus.ACTIVE.value]:
                summary.active_exposure_eur += total - covered
                summary.active_count += count
            elif status == ExposureStatus.PARTIALLY_COVERED.value:
                summary.pending_coverage_eur += total - covered
                summary.pending_count += count
            elif status == ExposureStatus.FULLY_COVERED.value:
                summary.fully_covered_eur += total
                summary.covered_count += count
            elif status == ExposureStatus.SETTLED.value:
                summary.settled_eur += total
                summary.settled_count += count
        
        # Calculate average coverage
        total_count = summary.active_count + summary.pending_count + summary.covered_count
        if total_count > 0:
            total_exposure = summary.active_exposure_eur + summary.pending_coverage_eur + summary.fully_covered_eur
            total_covered = summary.fully_covered_eur + (summary.pending_coverage_eur * 0.5)  # Approximate
            summary.average_coverage_percentage = (total_covered / total_exposure * 100) if total_exposure > 0 else 0
        
        # Get max single exposure
        max_doc = await self.exposure_collection.find_one(
            {"status": {"$in": [ExposureStatus.CREATED.value, ExposureStatus.ACTIVE.value]}},
            {"exposure_delta_eur": 1},
            sort=[("exposure_delta_eur", -1)]
        )
        if max_doc:
            summary.max_single_exposure_eur = max_doc.get("exposure_delta_eur", 0.0)
            if summary.active_exposure_eur > 0:
                summary.concentration_ratio = summary.max_single_exposure_eur / summary.active_exposure_eur
        
        return summary
    
    async def mark_exposure_for_batch(
        self,
        exposure_ids: List[str],
        batch_id: str
    ) -> int:
        """Mark exposures as part of a reconciliation batch."""
        result = await self.exposure_collection.update_many(
            {"exposure_id": {"$in": exposure_ids}},
            {
                "$set": {
                    "batch_id": batch_id,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        return result.modified_count
    
    async def reconstruct_exposure(self, exposure_id: str) -> Dict:
        """
        Reconstruct full exposure record with all references.
        
        Returns all linked data for audit trail reconstruction.
        """
        exposure = await self.get_exposure(exposure_id)
        if not exposure:
            return {"error": "Exposure not found"}
        
        reconstruction = {
            "exposure": exposure,
            "on_chain": {
                "deposit_tx_hash": exposure.get("deposit_tx_hash"),
                "deposit_block": exposure.get("deposit_block"),
                "crypto_amount": exposure.get("crypto_amount"),
                "crypto_currency": exposure.get("crypto_currency")
            },
            "payout": {
                "provider": exposure.get("payout_provider"),
                "reference": exposure.get("payout_reference"),
                "fiat_amount": exposure.get("fiat_amount"),
                "fiat_currency": exposure.get("fiat_currency")
            },
            "treasury_position": {
                "snapshot_id": exposure.get("treasury_snapshot_id"),
                "coverage_ratio_at_creation": exposure.get("treasury_coverage_ratio_at_creation")
            },
            "coverage": {
                "covered_amount_eur": exposure.get("covered_amount_eur", 0),
                "coverage_percentage": exposure.get("coverage_percentage", 0),
                "coverage_events": exposure.get("coverage_events", [])
            },
            "reconciliation": {
                "batch_id": exposure.get("batch_id"),
                "reconciled_at": exposure.get("reconciled_at"),
                "status": exposure.get("status")
            },
            "timestamps": {
                "created_at": exposure.get("created_at"),
                "updated_at": exposure.get("updated_at"),
                "settled_at": exposure.get("settled_at")
            }
        }
        
        return reconstruction
    
    async def mark_covered(
        self,
        exposure_id: str,
        coverage_amount: float,
        settlement_id: Optional[str] = None,
        ledger_entry_id: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Mark an exposure as covered (fully settled).
        
        Called when the payout is completed and the exposure is resolved.
        """
        now = datetime.now(timezone.utc)
        
        update = {
            "status": ExposureStatus.FULLY_COVERED.value,
            "covered_amount_eur": coverage_amount,
            "coverage_percentage": 100.0,
            "settled_at": now.isoformat(),
            "updated_at": now.isoformat()
        }
        
        if settlement_id:
            update["settlement_id"] = settlement_id
        if ledger_entry_id:
            update["ledger_entry_id"] = ledger_entry_id
        
        result = await self.exposure_collection.find_one_and_update(
            {"exposure_id": exposure_id},
            {"$set": update},
            return_document=True
        )
        
        if result:
            logger.info(f"Exposure {exposure_id} marked as FULLY_COVERED: €{coverage_amount:,.2f}")
            return {k: v for k, v in result.items() if k != "_id"}
        
        return None
    
    async def update_status(
        self,
        exposure_id: str,
        status: str,
        metadata: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Update exposure status with optional metadata.
        """
        now = datetime.now(timezone.utc)
        
        update = {
            "status": status,
            "updated_at": now.isoformat()
        }
        
        if metadata:
            for key, value in metadata.items():
                update[f"metadata.{key}"] = value
        
        result = await self.exposure_collection.find_one_and_update(
            {"exposure_id": exposure_id},
            {"$set": update},
            return_document=True
        )
        
        if result:
            logger.info(f"Exposure {exposure_id} status updated to {status}")
            return {k: v for k, v in result.items() if k != "_id"}
        
        return None


# Global instance
_exposure_service: Optional[ExposureService] = None


def get_exposure_service() -> Optional[ExposureService]:
    return _exposure_service


def set_exposure_service(service: ExposureService):
    global _exposure_service
    _exposure_service = service

"""
Batch Executor - Progressive TWAP-like Swap Execution.

Executes large swaps in smaller batches to minimize market impact:
- Micro-batch swaps (fragmented execution)
- Time-weighted execution (TWAP-like behavior)
- Adaptive slippage bounds
- Automatic pause on liquidity issues
"""

import os
import logging
import asyncio
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from dataclasses import dataclass, field
from enum import Enum
from motor.motor_asyncio import AsyncIOMotorDatabase

from .dex_service import (
    DEXService,
    SwapQuote,
    SwapResult,
    SwapStatus,
    NENO_ADDRESS,
    WBNB_ADDRESS,
    USDT_ADDRESS,
    USDC_ADDRESS,
    TOKEN_DECIMALS
)

logger = logging.getLogger(__name__)


class BatchStatus(str, Enum):
    """Batch execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchConfig:
    """Configuration for batch execution."""
    max_batch_size_eur: float = 500.0
    min_batch_interval_seconds: int = 300  # 5 minutes
    max_slippage_pct: float = 2.0
    max_price_impact_pct: float = 1.0
    max_batches: int = 20
    max_conversion_window_hours: int = 24
    pause_on_low_liquidity: bool = True
    min_liquidity_depth_eur: float = 10000.0
    
    def to_dict(self) -> Dict:
        return {
            "max_batch_size_eur": self.max_batch_size_eur,
            "min_batch_interval_seconds": self.min_batch_interval_seconds,
            "max_slippage_pct": self.max_slippage_pct,
            "max_price_impact_pct": self.max_price_impact_pct,
            "max_batches": self.max_batches,
            "max_conversion_window_hours": self.max_conversion_window_hours,
            "pause_on_low_liquidity": self.pause_on_low_liquidity,
            "min_liquidity_depth_eur": self.min_liquidity_depth_eur
        }


@dataclass
class BatchResult:
    """Result of a batch swap."""
    batch_id: str
    batch_index: int
    status: SwapStatus
    source_amount: int
    destination_amount: int
    source_amount_decimal: float
    destination_amount_decimal: float
    tx_hash: Optional[str] = None
    gas_cost_eur: float = 0
    slippage_pct: float = 0
    error_message: Optional[str] = None
    executed_at: Optional[str] = None


@dataclass
class ConversionJob:
    """A progressive conversion job."""
    job_id: str
    quote_id: str
    status: BatchStatus
    
    # Source/destination
    source_token: str
    destination_token: str
    total_source_amount: int
    total_source_amount_decimal: float
    
    # Target
    estimated_destination_amount: int
    estimated_destination_amount_decimal: float
    min_destination_amount: int
    
    # Progress
    source_amount_remaining: int
    source_amount_converted: int
    destination_amount_received: int
    destination_amount_decimal_received: float
    
    # Batches
    batch_config: BatchConfig
    batches: List[BatchResult] = field(default_factory=list)
    current_batch_index: int = 0
    
    # Timing
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    deadline: Optional[str] = None
    next_batch_at: Optional[str] = None
    
    # Audit
    total_gas_cost_eur: float = 0
    average_rate: float = 0
    total_slippage_pct: float = 0
    pause_reason: Optional[str] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "job_id": self.job_id,
            "quote_id": self.quote_id,
            "status": self.status.value,
            "source_token": self.source_token,
            "destination_token": self.destination_token,
            "total_source_amount": self.total_source_amount,
            "total_source_amount_decimal": self.total_source_amount_decimal,
            "estimated_destination_amount": self.estimated_destination_amount,
            "estimated_destination_amount_decimal": self.estimated_destination_amount_decimal,
            "min_destination_amount": self.min_destination_amount,
            "source_amount_remaining": self.source_amount_remaining,
            "source_amount_converted": self.source_amount_converted,
            "destination_amount_received": self.destination_amount_received,
            "destination_amount_decimal_received": self.destination_amount_decimal_received,
            "batch_config": self.batch_config.to_dict(),
            "batches": [
                {
                    "batch_id": b.batch_id,
                    "batch_index": b.batch_index,
                    "status": b.status.value,
                    "source_amount_decimal": b.source_amount_decimal,
                    "destination_amount_decimal": b.destination_amount_decimal,
                    "tx_hash": b.tx_hash,
                    "gas_cost_eur": b.gas_cost_eur,
                    "slippage_pct": b.slippage_pct,
                    "executed_at": b.executed_at
                }
                for b in self.batches
            ],
            "current_batch_index": self.current_batch_index,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "deadline": self.deadline,
            "next_batch_at": self.next_batch_at,
            "total_gas_cost_eur": self.total_gas_cost_eur,
            "average_rate": self.average_rate,
            "total_slippage_pct": self.total_slippage_pct,
            "pause_reason": self.pause_reason,
            "error_message": self.error_message
        }


class BatchExecutor:
    """
    Batch executor for progressive DEX swaps.
    
    Features:
    - TWAP-like execution (time-weighted)
    - Micro-batch fragmentation
    - Adaptive slippage control
    - Auto-pause on liquidity issues
    - Full audit trail per batch
    """
    
    def __init__(self, db: AsyncIOMotorDatabase, dex_service: DEXService):
        self.db = db
        self.dex_service = dex_service
        self.jobs_collection = db.conversion_jobs
        
        self._initialized = False
        self._active_jobs: Dict[str, ConversionJob] = {}
        self._executor_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Default config
        self._default_config = BatchConfig()
    
    async def initialize(self):
        """Initialize batch executor."""
        if self._initialized:
            return
        
        # Create indexes
        await self.jobs_collection.create_index("job_id", unique=True)
        await self.jobs_collection.create_index("quote_id")
        await self.jobs_collection.create_index("status")
        await self.jobs_collection.create_index("created_at")
        
        # Load pending jobs
        pending_jobs = await self.jobs_collection.find(
            {"status": {"$in": [BatchStatus.PENDING.value, BatchStatus.IN_PROGRESS.value, BatchStatus.PAUSED.value]}}
        ).to_list(100)
        
        for job_doc in pending_jobs:
            job = self._doc_to_job(job_doc)
            self._active_jobs[job.job_id] = job
        
        self._initialized = True
        logger.info(f"Batch Executor initialized with {len(self._active_jobs)} active jobs")
    
    def _doc_to_job(self, doc: Dict) -> ConversionJob:
        """Convert MongoDB document to ConversionJob."""
        config = BatchConfig(**doc.get("batch_config", {}))
        
        batches = []
        for b in doc.get("batches", []):
            batches.append(BatchResult(
                batch_id=b["batch_id"],
                batch_index=b["batch_index"],
                status=SwapStatus(b["status"]),
                source_amount=b.get("source_amount", 0),
                destination_amount=b.get("destination_amount", 0),
                source_amount_decimal=b.get("source_amount_decimal", 0),
                destination_amount_decimal=b.get("destination_amount_decimal", 0),
                tx_hash=b.get("tx_hash"),
                gas_cost_eur=b.get("gas_cost_eur", 0),
                slippage_pct=b.get("slippage_pct", 0),
                error_message=b.get("error_message"),
                executed_at=b.get("executed_at")
            ))
        
        return ConversionJob(
            job_id=doc["job_id"],
            quote_id=doc["quote_id"],
            status=BatchStatus(doc["status"]),
            source_token=doc["source_token"],
            destination_token=doc["destination_token"],
            total_source_amount=doc["total_source_amount"],
            total_source_amount_decimal=doc["total_source_amount_decimal"],
            estimated_destination_amount=doc["estimated_destination_amount"],
            estimated_destination_amount_decimal=doc["estimated_destination_amount_decimal"],
            min_destination_amount=doc["min_destination_amount"],
            source_amount_remaining=doc["source_amount_remaining"],
            source_amount_converted=doc["source_amount_converted"],
            destination_amount_received=doc["destination_amount_received"],
            destination_amount_decimal_received=doc["destination_amount_decimal_received"],
            batch_config=config,
            batches=batches,
            current_batch_index=doc.get("current_batch_index", 0),
            created_at=doc.get("created_at"),
            started_at=doc.get("started_at"),
            completed_at=doc.get("completed_at"),
            deadline=doc.get("deadline"),
            next_batch_at=doc.get("next_batch_at"),
            total_gas_cost_eur=doc.get("total_gas_cost_eur", 0),
            average_rate=doc.get("average_rate", 0),
            total_slippage_pct=doc.get("total_slippage_pct", 0),
            pause_reason=doc.get("pause_reason"),
            error_message=doc.get("error_message")
        )
    
    async def create_conversion_job(
        self,
        quote_id: str,
        source_token: str,
        destination_token: str,
        source_amount: int,
        source_amount_decimal: float,
        estimated_destination_amount: int,
        estimated_destination_amount_decimal: float,
        config: Optional[BatchConfig] = None
    ) -> ConversionJob:
        """Create a new progressive conversion job."""
        now = datetime.now(timezone.utc)
        config = config or self._default_config
        
        # Calculate min destination with slippage
        min_destination = int(estimated_destination_amount * (1 - config.max_slippage_pct / 100))
        
        # Calculate deadline
        deadline = (now + timedelta(hours=config.max_conversion_window_hours)).isoformat()
        
        job = ConversionJob(
            job_id=f"conv_{uuid4().hex[:12]}",
            quote_id=quote_id,
            status=BatchStatus.PENDING,
            source_token=source_token,
            destination_token=destination_token,
            total_source_amount=source_amount,
            total_source_amount_decimal=source_amount_decimal,
            estimated_destination_amount=estimated_destination_amount,
            estimated_destination_amount_decimal=estimated_destination_amount_decimal,
            min_destination_amount=min_destination,
            source_amount_remaining=source_amount,
            source_amount_converted=0,
            destination_amount_received=0,
            destination_amount_decimal_received=0,
            batch_config=config,
            created_at=now.isoformat(),
            deadline=deadline
        )
        
        # Store in database
        await self.jobs_collection.insert_one(job.to_dict())
        
        # Add to active jobs
        self._active_jobs[job.job_id] = job
        
        logger.info(
            f"[BATCH] Conversion job created: {job.job_id} | "
            f"{source_amount_decimal:.6f} {source_token} → {destination_token} | "
            f"Deadline: {deadline}"
        )
        
        return job
    
    async def start_conversion(self, job_id: str) -> ConversionJob:
        """Start or resume a conversion job."""
        job = self._active_jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        if job.status == BatchStatus.COMPLETED:
            return job
        
        if job.status == BatchStatus.CANCELLED:
            raise ValueError("Cannot start cancelled job")
        
        now = datetime.now(timezone.utc)
        job.status = BatchStatus.IN_PROGRESS
        job.started_at = job.started_at or now.isoformat()
        job.next_batch_at = now.isoformat()
        
        await self._update_job(job)
        
        logger.info(f"[BATCH] Conversion started: {job.job_id}")
        
        return job
    
    async def execute_next_batch(self, job_id: str) -> Tuple[ConversionJob, Optional[BatchResult]]:
        """Execute the next batch in a conversion job."""
        job = self._active_jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        if job.status != BatchStatus.IN_PROGRESS:
            return job, None
        
        now = datetime.now(timezone.utc)
        
        # Check deadline
        if job.deadline and now.isoformat() > job.deadline:
            job.status = BatchStatus.PAUSED
            job.pause_reason = "Deadline exceeded"
            await self._update_job(job)
            return job, None
        
        # Check max batches
        if job.current_batch_index >= job.batch_config.max_batches:
            job.status = BatchStatus.PAUSED
            job.pause_reason = "Max batches reached"
            await self._update_job(job)
            return job, None
        
        # Check if any source amount remaining
        if job.source_amount_remaining <= 0:
            job.status = BatchStatus.COMPLETED
            job.completed_at = now.isoformat()
            await self._update_job(job)
            return job, None
        
        # Calculate batch size
        # Use EUR equivalent to determine batch size
        neno_price_eur = 10000.0  # Approximate NENO price
        src_decimals = TOKEN_DECIMALS.get(job.source_token.lower(), 18)
        source_amount_eur = (job.source_amount_remaining / (10 ** src_decimals)) * neno_price_eur
        
        max_batch_eur = job.batch_config.max_batch_size_eur
        
        if source_amount_eur <= max_batch_eur:
            # Final batch - use remaining amount
            batch_source_amount = job.source_amount_remaining
        else:
            # Calculate proportional batch
            batch_ratio = max_batch_eur / source_amount_eur
            batch_source_amount = int(job.source_amount_remaining * batch_ratio)
        
        # Get quote for batch
        quote = await self.dex_service.get_best_quote(
            job.source_token,
            job.destination_token,
            batch_source_amount
        )
        
        if not quote:
            job.status = BatchStatus.PAUSED
            job.pause_reason = "No liquidity available"
            await self._update_job(job)
            return job, None
        
        # Check price impact
        if quote.price_impact_pct > job.batch_config.max_price_impact_pct:
            job.status = BatchStatus.PAUSED
            job.pause_reason = f"Price impact too high: {quote.price_impact_pct:.2f}%"
            await self._update_job(job)
            return job, None
        
        # Calculate minReturn with slippage
        min_return = int(quote.destination_amount * (1 - job.batch_config.max_slippage_pct / 100))
        
        # Execute swap
        batch_id = f"batch_{job.job_id}_{job.current_batch_index}"
        
        swap_result = await self.dex_service.execute_swap_1inch(
            source_token=job.source_token,
            destination_token=job.destination_token,
            amount_wei=batch_source_amount,
            min_return=min_return,
            quote_id=quote.quote_id
        )
        
        # Create batch result
        batch = BatchResult(
            batch_id=batch_id,
            batch_index=job.current_batch_index,
            status=swap_result.status,
            source_amount=batch_source_amount,
            destination_amount=swap_result.destination_amount,
            source_amount_decimal=swap_result.source_amount_decimal,
            destination_amount_decimal=swap_result.destination_amount_decimal,
            tx_hash=swap_result.tx_hash,
            gas_cost_eur=swap_result.gas_cost_eur,
            slippage_pct=swap_result.slippage_pct,
            error_message=swap_result.error_message,
            executed_at=now.isoformat()
        )
        
        job.batches.append(batch)
        job.current_batch_index += 1
        
        if swap_result.status == SwapStatus.COMPLETED:
            # Update progress
            job.source_amount_converted += batch_source_amount
            job.source_amount_remaining -= batch_source_amount
            job.destination_amount_received += swap_result.destination_amount
            
            dst_decimals = TOKEN_DECIMALS.get(job.destination_token.lower(), 18)
            job.destination_amount_decimal_received = job.destination_amount_received / (10 ** dst_decimals)
            
            job.total_gas_cost_eur += swap_result.gas_cost_eur
            
            # Calculate average rate
            src_decimals = TOKEN_DECIMALS.get(job.source_token.lower(), 18)
            total_src = job.source_amount_converted / (10 ** src_decimals)
            job.average_rate = job.destination_amount_decimal_received / total_src if total_src > 0 else 0
            
            # Schedule next batch
            next_batch_time = now + timedelta(seconds=job.batch_config.min_batch_interval_seconds)
            job.next_batch_at = next_batch_time.isoformat()
            
            # Check if complete
            if job.source_amount_remaining <= 0:
                job.status = BatchStatus.COMPLETED
                job.completed_at = now.isoformat()
            
            logger.info(
                f"[BATCH] Batch {job.current_batch_index - 1} COMPLETED: "
                f"{batch.source_amount_decimal:.6f} → {batch.destination_amount_decimal:.6f} | "
                f"Remaining: {job.source_amount_remaining / (10 ** src_decimals):.6f}"
            )
        else:
            job.status = BatchStatus.PAUSED
            job.pause_reason = f"Batch failed: {swap_result.error_message}"
            
            logger.error(
                f"[BATCH] Batch {job.current_batch_index - 1} FAILED: {swap_result.error_message}"
            )
        
        await self._update_job(job)
        
        return job, batch
    
    async def pause_conversion(self, job_id: str, reason: str) -> ConversionJob:
        """Pause a conversion job."""
        job = self._active_jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        job.status = BatchStatus.PAUSED
        job.pause_reason = reason
        
        await self._update_job(job)
        
        logger.info(f"[BATCH] Conversion paused: {job.job_id} - {reason}")
        
        return job
    
    async def resume_conversion(self, job_id: str) -> ConversionJob:
        """Resume a paused conversion job."""
        job = self._active_jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        if job.status != BatchStatus.PAUSED:
            return job
        
        job.status = BatchStatus.IN_PROGRESS
        job.pause_reason = None
        job.next_batch_at = datetime.now(timezone.utc).isoformat()
        
        await self._update_job(job)
        
        logger.info(f"[BATCH] Conversion resumed: {job.job_id}")
        
        return job
    
    async def cancel_conversion(self, job_id: str, reason: str) -> ConversionJob:
        """Cancel a conversion job."""
        job = self._active_jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        if job.status == BatchStatus.COMPLETED:
            raise ValueError("Cannot cancel completed job")
        
        job.status = BatchStatus.CANCELLED
        job.error_message = reason
        job.completed_at = datetime.now(timezone.utc).isoformat()
        
        await self._update_job(job)
        
        # Remove from active jobs
        del self._active_jobs[job_id]
        
        logger.info(f"[BATCH] Conversion cancelled: {job.job_id} - {reason}")
        
        return job
    
    async def get_job(self, job_id: str) -> Optional[ConversionJob]:
        """Get a conversion job by ID."""
        if job_id in self._active_jobs:
            return self._active_jobs[job_id]
        
        doc = await self.jobs_collection.find_one({"job_id": job_id})
        if doc:
            return self._doc_to_job(doc)
        
        return None
    
    async def get_job_by_quote(self, quote_id: str) -> Optional[ConversionJob]:
        """Get a conversion job by quote ID."""
        for job in self._active_jobs.values():
            if job.quote_id == quote_id:
                return job
        
        doc = await self.jobs_collection.find_one({"quote_id": quote_id})
        if doc:
            return self._doc_to_job(doc)
        
        return None
    
    async def _update_job(self, job: ConversionJob):
        """Update job in database."""
        await self.jobs_collection.update_one(
            {"job_id": job.job_id},
            {"$set": job.to_dict()}
        )
    
    async def start_executor_worker(self):
        """Start background worker to process batches."""
        if self._running:
            return
        
        self._running = True
        self._executor_task = asyncio.create_task(self._executor_loop())
        logger.info("[BATCH] Executor worker started")
    
    async def stop_executor_worker(self):
        """Stop background worker."""
        self._running = False
        if self._executor_task:
            self._executor_task.cancel()
            try:
                await self._executor_task
            except asyncio.CancelledError:
                pass
        logger.info("[BATCH] Executor worker stopped")
    
    async def _executor_loop(self):
        """Background loop to process pending batches."""
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                
                for job_id, job in list(self._active_jobs.items()):
                    if job.status != BatchStatus.IN_PROGRESS:
                        continue
                    
                    # Check if it's time for next batch
                    if job.next_batch_at and now.isoformat() >= job.next_batch_at:
                        await self.execute_next_batch(job_id)
                
                # Sleep between checks
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"[BATCH] Executor error: {e}")
                await asyncio.sleep(30)
    
    async def get_executor_status(self) -> Dict:
        """Get batch executor status."""
        active_count = len([j for j in self._active_jobs.values() if j.status == BatchStatus.IN_PROGRESS])
        paused_count = len([j for j in self._active_jobs.values() if j.status == BatchStatus.PAUSED])
        pending_count = len([j for j in self._active_jobs.values() if j.status == BatchStatus.PENDING])
        
        return {
            "running": self._running,
            "active_jobs": active_count,
            "paused_jobs": paused_count,
            "pending_jobs": pending_count,
            "total_jobs": len(self._active_jobs),
            "default_config": self._default_config.to_dict()
        }

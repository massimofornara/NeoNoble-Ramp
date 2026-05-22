"""
Hedging Service.

Manages exposure hedging including:
- Exposure threshold monitoring
- Policy-driven hedge triggers
- Hedge execution (shadow mode)
- Volatility guards
- Batch hedge windows

Phase 1: Shadow mode - all hedges are proposed and logged, not executed.
"""

import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.liquidity.hedge_models import (
    HedgeTriggerType,
    HedgeMode,
    HedgeStatus,
    HedgePolicy,
    HedgeEvent,
    HedgeProposal
)

logger = logging.getLogger(__name__)


class HedgingService:
    """
    Hedging service for exposure risk management.
    
    Features:
    - Policy-based hedge triggers
    - Exposure threshold monitoring
    - Volatility guard (lock hedging during high volatility)
    - Batch hedge windows
    - Shadow mode (proposal-only)
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.hedges_collection = db.hedge_events
        self.proposals_collection = db.hedge_proposals
        self.policy_collection = db.hedge_policies
        
        self._initialized = False
        self._default_policy: Optional[HedgePolicy] = None
        self._volatility_locked = False
        self._volatility_lock_until: Optional[datetime] = None
        self._last_batch_time: Optional[datetime] = None
    
    async def initialize(self):
        """Initialize hedging service."""
        if self._initialized:
            return
        
        # Create indexes
        await self.hedges_collection.create_index("hedge_id", unique=True)
        await self.hedges_collection.create_index("status")
        await self.hedges_collection.create_index("created_at")
        await self.hedges_collection.create_index("exposure_ids")
        await self.proposals_collection.create_index("proposal_id", unique=True)
        await self.proposals_collection.create_index("triggered_at")
        await self.policy_collection.create_index("policy_id", unique=True)
        
        # Load or create default policy
        self._default_policy = await self._load_or_create_default_policy()
        
        self._initialized = True
        logger.info(
            f"Hedging Service initialized:\n"
            f"  Policy: {self._default_policy.name}\n"
            f"  Exposure Threshold: {self._default_policy.exposure_threshold_pct * 100}%\n"
            f"  Batch Window: {self._default_policy.batch_window_hours}h\n"
            f"  Volatility Guard: {'Enabled' if self._default_policy.volatility_guard_enabled else 'Disabled'}\n"
            f"  Shadow Mode: {self._default_policy.shadow_mode}"
        )
    
    async def _load_or_create_default_policy(self) -> HedgePolicy:
        """Load or create default hedge policy."""
        policy_doc = await self.policy_collection.find_one({"policy_id": "default"})
        
        if policy_doc:
            return HedgePolicy(
                policy_id=policy_doc.get("policy_id"),
                name=policy_doc.get("name"),
                enabled=policy_doc.get("enabled", True),
                exposure_threshold_eur=policy_doc.get("exposure_threshold_eur", 75000.0),
                exposure_threshold_pct=policy_doc.get("exposure_threshold_pct", 0.75),
                coverage_ratio_trigger=policy_doc.get("coverage_ratio_trigger", 0.75),
                batch_window_hours=policy_doc.get("batch_window_hours", 12),
                batch_enabled=policy_doc.get("batch_enabled", True),
                volatility_guard_enabled=policy_doc.get("volatility_guard_enabled", True),
                volatility_threshold_pct=policy_doc.get("volatility_threshold_pct", 5.0),
                volatility_lock_duration_hours=policy_doc.get("volatility_lock_duration_hours", 2),
                default_mode=HedgeMode(policy_doc.get("default_mode", "deferred")),
                max_single_hedge_eur=policy_doc.get("max_single_hedge_eur", 100000.0),
                min_hedge_amount_eur=policy_doc.get("min_hedge_amount_eur", 1000.0),
                shadow_mode=policy_doc.get("shadow_mode", True)
            )
        
        # Create default policy (Custom Conservative Hybrid as requested)
        policy = HedgePolicy(
            policy_id="default",
            name="Conservative Hybrid Policy",
            enabled=True,
            exposure_threshold_eur=75000.0,      # €75k threshold
            exposure_threshold_pct=0.75,          # 75% coverage threshold
            coverage_ratio_trigger=0.75,          # Trigger when ratio below 75%
            batch_window_hours=12,                # 12-hour batch window
            batch_enabled=True,
            volatility_guard_enabled=True,        # Enable volatility lock
            volatility_threshold_pct=5.0,         # 5% price move triggers lock
            volatility_lock_duration_hours=2,     # Lock for 2 hours
            default_mode=HedgeMode.DEFERRED,      # Deferred by default
            max_single_hedge_eur=100000.0,
            min_hedge_amount_eur=1000.0,
            shadow_mode=True                      # Shadow mode for Phase 1
        )
        
        await self.policy_collection.insert_one({
            **policy.to_dict(),
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        return policy
    
    async def evaluate_hedge_triggers(
        self,
        total_exposure_eur: float,
        coverage_ratio: float,
        active_exposure_ids: List[str]
    ) -> Optional[HedgeProposal]:
        """
        Evaluate if hedge triggers are met.
        
        Returns a HedgeProposal if hedge is recommended.
        """
        if not self._default_policy.enabled:
            return None
        
        # Check volatility lock
        if self._is_volatility_locked():
            logger.debug("Hedge evaluation skipped: volatility lock active")
            return None
        
        now = datetime.now(timezone.utc)
        trigger_type = None
        trigger_reason = None
        proposed_mode = self._default_policy.default_mode
        
        # Check coverage ratio trigger
        if coverage_ratio < self._default_policy.coverage_ratio_trigger:
            trigger_type = HedgeTriggerType.COVERAGE_RATIO
            trigger_reason = f"Coverage ratio {coverage_ratio:.2%} below threshold {self._default_policy.coverage_ratio_trigger:.2%}"
        
        # Check exposure threshold
        elif total_exposure_eur >= self._default_policy.exposure_threshold_eur:
            trigger_type = HedgeTriggerType.THRESHOLD
            trigger_reason = f"Exposure €{total_exposure_eur:,.2f} exceeds threshold €{self._default_policy.exposure_threshold_eur:,.2f}"
        
        # Check batch window
        elif self._default_policy.batch_enabled:
            if self._last_batch_time is None:
                self._last_batch_time = now
            
            hours_since_batch = (now - self._last_batch_time).total_seconds() / 3600
            if hours_since_batch >= self._default_policy.batch_window_hours:
                trigger_type = HedgeTriggerType.BATCH_WINDOW
                trigger_reason = f"Batch window reached: {hours_since_batch:.1f}h since last batch"
                proposed_mode = HedgeMode.DEFERRED
        
        if trigger_type is None:
            return None
        
        # Calculate proposed hedge amount
        if coverage_ratio < 1.0:
            # Need to cover the gap
            coverage_gap = (1.0 - coverage_ratio) * total_exposure_eur
            proposed_amount = min(coverage_gap, self._default_policy.max_single_hedge_eur)
        else:
            # Hedge a portion of exposure
            proposed_amount = min(
                total_exposure_eur * 0.5,  # Hedge 50% of exposure
                self._default_policy.max_single_hedge_eur
            )
        
        # Check minimum
        if proposed_amount < self._default_policy.min_hedge_amount_eur:
            return None
        
        # Create proposal
        proposal = HedgeProposal(
            proposal_id=f"prop_{uuid4().hex[:12]}",
            trigger_type=trigger_type,
            trigger_reason=trigger_reason,
            triggered_at=now.isoformat(),
            proposed_mode=proposed_mode,
            proposed_amount_eur=proposed_amount,
            proposed_exposure_ids=active_exposure_ids[:10],  # Limit to 10
            current_exposure_eur=total_exposure_eur,
            exposure_after_hedge_eur=total_exposure_eur - proposed_amount,
            current_coverage_ratio=coverage_ratio,
            coverage_ratio_after_hedge=coverage_ratio + (proposed_amount / total_exposure_eur) if total_exposure_eur > 0 else 1.0,
            valid_until=(now + timedelta(hours=1)).isoformat(),
            policy_id=self._default_policy.policy_id
        )
        
        # Store proposal
        await self.proposals_collection.insert_one(proposal.to_dict())
        
        logger.info(
            f"[SHADOW] Hedge Proposal: {proposal.proposal_id} | "
            f"Trigger: {trigger_type.value} | "
            f"Amount: €{proposed_amount:,.2f} | "
            f"Reason: {trigger_reason}"
        )
        
        return proposal
    
    async def create_hedge_event(
        self,
        proposal: Optional[HedgeProposal] = None,
        trigger_type: HedgeTriggerType = HedgeTriggerType.MANUAL,
        trigger_reason: str = "Manual hedge",
        mode: HedgeMode = HedgeMode.DEFERRED,
        target_amount_eur: float = 0.0,
        exposure_ids: List[str] = None,
        exposures_before_eur: float = 0.0,
        coverage_ratio_before: float = 0.0
    ) -> HedgeEvent:
        """
        Create a hedge event.
        
        In shadow mode, this logs the hedge but doesn't execute real conversions.
        """
        now = datetime.now(timezone.utc)
        
        # Use proposal values if provided
        if proposal:
            trigger_type = proposal.trigger_type
            trigger_reason = proposal.trigger_reason
            mode = proposal.proposed_mode
            target_amount_eur = proposal.proposed_amount_eur
            exposure_ids = proposal.proposed_exposure_ids
            exposures_before_eur = proposal.current_exposure_eur
            coverage_ratio_before = proposal.current_coverage_ratio
        
        event = HedgeEvent(
            hedge_id=f"hedge_{uuid4().hex[:12]}",
            status=HedgeStatus.PROPOSED if self._default_policy.shadow_mode else HedgeStatus.QUEUED,
            trigger_type=trigger_type,
            trigger_reason=trigger_reason,
            policy_id=self._default_policy.policy_id,
            proposal_id=proposal.proposal_id if proposal else None,
            mode=mode,
            target_amount_eur=target_amount_eur,
            remaining_amount_eur=target_amount_eur,
            exposure_ids=exposure_ids or [],
            exposures_before_eur=exposures_before_eur,
            coverage_ratio_before=coverage_ratio_before,
            is_shadow=self._default_policy.shadow_mode,
            created_at=now.isoformat()
        )
        
        if self._default_policy.shadow_mode:
            # Shadow execution - simulate hedge
            event.status = HedgeStatus.COMPLETED
            event.executed_amount_eur = target_amount_eur
            event.remaining_amount_eur = 0.0
            event.exposures_after_eur = exposures_before_eur - target_amount_eur
            event.coverage_ratio_after = (
                coverage_ratio_before + (target_amount_eur / exposures_before_eur)
                if exposures_before_eur > 0 else 1.0
            )
            event.completed_at = now.isoformat()
            
            # Simulate costs
            event.total_cost_eur = target_amount_eur * 0.003  # 0.3% total cost
            event.slippage_cost_eur = target_amount_eur * 0.002
            event.fee_cost_eur = target_amount_eur * 0.001
            
            event.shadow_execution_log = {
                "simulated": True,
                "executed_at": now.isoformat(),
                "target_achieved": True,
                "conversion_path": ["NENO", "BNB", "USDT", "EUR"],
                "estimated_market_impact": "minimal"
            }
        
        # Store event
        await self.hedges_collection.insert_one(event.to_dict())
        
        logger.info(
            f"[{'SHADOW' if event.is_shadow else 'LIVE'}] Hedge Event: {event.hedge_id} | "
            f"Amount: €{target_amount_eur:,.2f} | "
            f"Status: {event.status.value} | "
            f"Trigger: {trigger_type.value}"
        )
        
        return event
    
    def _is_volatility_locked(self) -> bool:
        """Check if volatility lock is active."""
        if not self._default_policy.volatility_guard_enabled:
            return False
        
        if not self._volatility_locked:
            return False
        
        now = datetime.now(timezone.utc)
        if self._volatility_lock_until and now >= self._volatility_lock_until:
            self._volatility_locked = False
            self._volatility_lock_until = None
            logger.info("Volatility lock expired")
            return False
        
        return True
    
    async def trigger_volatility_lock(self, reason: str = "High volatility detected"):
        """Trigger volatility lock."""
        if not self._default_policy.volatility_guard_enabled:
            return
        
        now = datetime.now(timezone.utc)
        self._volatility_locked = True
        self._volatility_lock_until = now + timedelta(
            hours=self._default_policy.volatility_lock_duration_hours
        )
        
        logger.warning(
            f"Volatility lock ACTIVATED until {self._volatility_lock_until.isoformat()} | "
            f"Reason: {reason}"
        )
    
    async def get_hedge(self, hedge_id: str) -> Optional[Dict]:
        """Get hedge by ID."""
        doc = await self.hedges_collection.find_one(
            {"hedge_id": hedge_id},
            {"_id": 0}
        )
        return doc
    
    async def get_recent_hedges(self, limit: int = 50) -> List[Dict]:
        """Get recent hedge events."""
        cursor = self.hedges_collection.find(
            {},
            {"_id": 0}
        ).sort("created_at", -1).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def get_pending_hedges(self) -> List[Dict]:
        """Get pending (non-completed) hedges."""
        cursor = self.hedges_collection.find(
            {"status": {"$in": [
                HedgeStatus.QUEUED.value,
                HedgeStatus.EXECUTING.value,
                HedgeStatus.PARTIAL.value
            ]}},
            {"_id": 0}
        ).sort("created_at", 1)
        
        return await cursor.to_list(length=100)
    
    async def get_recent_proposals(self, limit: int = 20) -> List[Dict]:
        """Get recent hedge proposals (shadow mode output)."""
        cursor = self.proposals_collection.find(
            {},
            {"_id": 0}
        ).sort("triggered_at", -1).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def get_hedging_summary(self) -> Dict:
        """Get hedging service summary."""
        # Aggregate hedges by status
        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "total_amount": {"$sum": "$executed_amount_eur"},
                    "total_cost": {"$sum": "$total_cost_eur"}
                }
            }
        ]
        
        results = await self.hedges_collection.aggregate(pipeline).to_list(length=20)
        
        # Get recent proposals
        recent_proposals = await self.get_recent_proposals(limit=5)
        
        return {
            "policy": self._default_policy.to_dict(),
            "volatility_locked": self._is_volatility_locked(),
            "volatility_lock_until": self._volatility_lock_until.isoformat() if self._volatility_lock_until else None,
            "last_batch_time": self._last_batch_time.isoformat() if self._last_batch_time else None,
            "by_status": {r["_id"]: {
                "count": r["count"],
                "total_amount": r["total_amount"],
                "total_cost": r["total_cost"]
            } for r in results},
            "recent_proposals": recent_proposals,
            "shadow_mode": self._default_policy.shadow_mode
        }
    
    async def update_policy(self, updates: Dict) -> HedgePolicy:
        """Update hedge policy configuration."""
        now = datetime.now(timezone.utc)
        
        # Update policy document
        await self.policy_collection.update_one(
            {"policy_id": "default"},
            {
                "$set": {
                    **updates,
                    "updated_at": now.isoformat()
                }
            }
        )
        
        # Reload policy
        self._default_policy = await self._load_or_create_default_policy()
        
        logger.info(f"Hedge policy updated: {updates}")
        return self._default_policy
    
    async def execute_real_hedge(
        self,
        hedge_id: str,
        connector_manager = None
    ) -> Tuple[HedgeEvent, Optional[str]]:
        """
        Execute a real hedge through exchange connectors.
        
        Phase 3: Live hedge execution via Binance/Kraken.
        
        Args:
            hedge_id: ID of the hedge event to execute
            connector_manager: ConnectorManager instance for exchange access
            
        Returns:
            Tuple of (updated HedgeEvent, error_message)
        """
        from services.exchanges import get_connector_manager, OrderSide
        
        now = datetime.now(timezone.utc)
        connector_manager = connector_manager or get_connector_manager()
        
        # Get hedge event
        hedge_doc = await self.hedges_collection.find_one({"hedge_id": hedge_id})
        if not hedge_doc:
            return None, f"Hedge not found: {hedge_id}"
        
        # Check if already executed
        if hedge_doc.get("status") == HedgeStatus.COMPLETED.value:
            return self._doc_to_event(hedge_doc), "Hedge already completed"
        
        # Check policy
        if self._default_policy.shadow_mode:
            logger.warning(f"[HEDGE] Cannot execute real hedge in shadow mode: {hedge_id}")
            return self._doc_to_event(hedge_doc), "Shadow mode enabled - use update_policy to disable"
        
        # Check connector
        if not connector_manager or not connector_manager.is_enabled():
            logger.warning(f"[HEDGE] Connector manager not enabled: {hedge_id}")
            return self._doc_to_event(hedge_doc), "Exchange connectors not enabled"
        
        target_amount = hedge_doc.get("target_amount_eur", 0)
        
        # Update status to executing
        await self.hedges_collection.update_one(
            {"hedge_id": hedge_id},
            {"$set": {"status": HedgeStatus.EXECUTING.value, "execution_started_at": now.isoformat()}}
        )
        
        try:
            # Execute hedge as market sell order
            # Convert EUR amount to BNB quantity (approximate)
            # In production, this would use real-time prices
            bnb_price_eur = 300.0  # Approximate - should fetch from connector
            quantity = target_amount / bnb_price_eur
            
            # Execute order
            order, error = await connector_manager.execute_order(
                symbol="BNBEUR",  # or BNBUSDT on Binance
                side=OrderSide.SELL,
                quantity=quantity,
                client_order_id=hedge_id
            )
            
            if error:
                # Hedge execution failed
                await self.hedges_collection.update_one(
                    {"hedge_id": hedge_id},
                    {
                        "$set": {
                            "status": HedgeStatus.FAILED.value,
                            "error_message": error,
                            "failed_at": now.isoformat()
                        }
                    }
                )
                return self._doc_to_event(await self.hedges_collection.find_one({"hedge_id": hedge_id})), error
            
            # Calculate executed amount
            executed_eur = order.filled_quantity * order.average_price if order.average_price > 0 else target_amount
            
            # Update hedge as completed
            await self.hedges_collection.update_one(
                {"hedge_id": hedge_id},
                {
                    "$set": {
                        "status": HedgeStatus.COMPLETED.value,
                        "executed_amount_eur": executed_eur,
                        "remaining_amount_eur": max(0, target_amount - executed_eur),
                        "exposures_after_eur": hedge_doc.get("exposures_before_eur", 0) - executed_eur,
                        "coverage_ratio_after": min(1.0, hedge_doc.get("coverage_ratio_before", 0) + 
                            (executed_eur / hedge_doc.get("exposures_before_eur", 1) if hedge_doc.get("exposures_before_eur", 0) > 0 else 0)),
                        "completed_at": now.isoformat(),
                        "total_cost_eur": order.fee,
                        "slippage_cost_eur": abs(executed_eur - target_amount),
                        "fee_cost_eur": order.fee,
                        "execution_details": {
                            "exchange": order.exchange,
                            "order_id": order.order_id,
                            "exchange_order_id": order.exchange_order_id,
                            "filled_quantity": order.filled_quantity,
                            "average_price": order.average_price,
                            "fee": order.fee,
                            "fee_currency": order.fee_currency
                        }
                    }
                }
            )
            
            logger.info(
                f"[HEDGE:LIVE] Executed: {hedge_id} | "
                f"Amount: €{executed_eur:,.2f} | "
                f"Order: {order.exchange_order_id}"
            )
            
            return self._doc_to_event(await self.hedges_collection.find_one({"hedge_id": hedge_id})), None
            
        except Exception as e:
            logger.error(f"[HEDGE] Execution error: {e}")
            await self.hedges_collection.update_one(
                {"hedge_id": hedge_id},
                {
                    "$set": {
                        "status": HedgeStatus.FAILED.value,
                        "error_message": str(e),
                        "failed_at": now.isoformat()
                    }
                }
            )
            return self._doc_to_event(await self.hedges_collection.find_one({"hedge_id": hedge_id})), str(e)
    
    def _doc_to_event(self, doc: Dict) -> Optional[HedgeEvent]:
        """Convert MongoDB document to HedgeEvent."""
        if not doc:
            return None
        return HedgeEvent(
            hedge_id=doc["hedge_id"],
            status=HedgeStatus(doc["status"]),
            trigger_type=HedgeTriggerType(doc.get("trigger_type", "manual")),
            trigger_reason=doc.get("trigger_reason", ""),
            policy_id=doc.get("policy_id"),
            proposal_id=doc.get("proposal_id"),
            mode=HedgeMode(doc.get("mode", "deferred")),
            target_amount_eur=doc.get("target_amount_eur", 0),
            executed_amount_eur=doc.get("executed_amount_eur", 0),
            remaining_amount_eur=doc.get("remaining_amount_eur", 0),
            exposure_ids=doc.get("exposure_ids", []),
            exposures_before_eur=doc.get("exposures_before_eur", 0),
            exposures_after_eur=doc.get("exposures_after_eur", 0),
            coverage_ratio_before=doc.get("coverage_ratio_before", 0),
            coverage_ratio_after=doc.get("coverage_ratio_after", 0),
            total_cost_eur=doc.get("total_cost_eur", 0),
            slippage_cost_eur=doc.get("slippage_cost_eur", 0),
            fee_cost_eur=doc.get("fee_cost_eur", 0),
            is_shadow=doc.get("is_shadow", True),
            created_at=doc.get("created_at"),
            completed_at=doc.get("completed_at")
        )
    
    async def enable_live_hedging(self, user_id: str = None):
        """Enable live hedge execution (disable shadow mode)."""
        await self.update_policy({"shadow_mode": False})
        logger.info(f"[HEDGE] LIVE HEDGING ENABLED by {user_id}")
    
    async def disable_live_hedging(self, reason: str = None):
        """Disable live hedging (enable shadow mode)."""
        await self.update_policy({"shadow_mode": True})
        logger.warning(f"[HEDGE] LIVE HEDGING DISABLED: {reason}")


# Global instance
_hedging_service: Optional[HedgingService] = None


def get_hedging_service() -> Optional[HedgingService]:
    return _hedging_service


def set_hedging_service(service: HedgingService):
    global _hedging_service
    _hedging_service = service

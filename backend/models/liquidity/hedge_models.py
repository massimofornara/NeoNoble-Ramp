"""
Hedge Event Models.

Defines data structures for hedging operations:
- Hedge policies and triggers
- Hedge events and proposals
- Hedge execution modes
"""

from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timezone


class HedgeTriggerType(Enum):
    """Types of hedge triggers."""
    THRESHOLD = "threshold"           # Exposure threshold reached
    VOLATILITY = "volatility"         # Volatility event detected
    COVERAGE_RATIO = "coverage_ratio" # Coverage ratio below target
    BATCH_WINDOW = "batch_window"     # Scheduled batch window
    MANUAL = "manual"                 # Manual trigger
    POLICY_OVERRIDE = "policy_override"  # Policy override


class HedgeMode(Enum):
    """Hedge execution modes."""
    FULL = "full"                     # Full exposure hedge
    PARTIAL = "partial"               # Partial exposure hedge
    DEFERRED = "deferred"             # Deferred to batch window
    IMMEDIATE = "immediate"           # Immediate execution


class HedgeStatus(Enum):
    """Hedge event status."""
    PROPOSED = "proposed"             # Hedge proposed (shadow mode)
    APPROVED = "approved"             # Approved for execution
    QUEUED = "queued"                 # Queued for execution
    EXECUTING = "executing"           # Currently executing
    PARTIAL = "partial"               # Partially executed
    COMPLETED = "completed"           # Fully executed
    FAILED = "failed"                 # Execution failed
    CANCELLED = "cancelled"           # Cancelled
    EXPIRED = "expired"               # Proposal expired


@dataclass
class HedgePolicy:
    """Hedge policy configuration."""
    policy_id: str
    name: str
    enabled: bool = True
    
    # Trigger thresholds
    exposure_threshold_eur: float = 75000.0    # 75% of €100k = €75k
    exposure_threshold_pct: float = 0.75       # 75% coverage threshold
    coverage_ratio_trigger: float = 0.75       # Trigger when ratio below this
    
    # Batch settings
    batch_window_hours: int = 12               # 12-hour batch window
    batch_enabled: bool = True
    
    # Volatility guard
    volatility_guard_enabled: bool = True
    volatility_threshold_pct: float = 5.0      # 5% price move triggers lock
    volatility_lock_duration_hours: int = 2    # Lock hedging for 2 hours
    
    # Execution settings
    default_mode: HedgeMode = HedgeMode.DEFERRED
    max_single_hedge_eur: float = 100000.0     # Max single hedge
    min_hedge_amount_eur: float = 1000.0       # Minimum hedge amount
    
    # Shadow mode
    shadow_mode: bool = True                   # Log-only, no real execution
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "enabled": self.enabled,
            "exposure_threshold_eur": self.exposure_threshold_eur,
            "exposure_threshold_pct": self.exposure_threshold_pct,
            "coverage_ratio_trigger": self.coverage_ratio_trigger,
            "batch_window_hours": self.batch_window_hours,
            "batch_enabled": self.batch_enabled,
            "volatility_guard_enabled": self.volatility_guard_enabled,
            "volatility_threshold_pct": self.volatility_threshold_pct,
            "volatility_lock_duration_hours": self.volatility_lock_duration_hours,
            "default_mode": self.default_mode.value,
            "max_single_hedge_eur": self.max_single_hedge_eur,
            "min_hedge_amount_eur": self.min_hedge_amount_eur,
            "shadow_mode": self.shadow_mode,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


@dataclass
class HedgeProposal:
    """A proposed hedge action (shadow mode output)."""
    proposal_id: str
    
    # Trigger info
    trigger_type: HedgeTriggerType
    trigger_reason: str
    triggered_at: str
    
    # Proposed hedge
    proposed_mode: HedgeMode
    proposed_amount_eur: float
    proposed_exposure_ids: List[str]          # Exposures to cover
    
    # Hypothetical routing
    hypothetical_path: Optional[Dict] = None  # Routing that would be used
    hypothetical_rate: float = 0.0            # Expected rate
    hypothetical_cost_eur: float = 0.0        # Expected cost
    
    # Treasury impact
    current_exposure_eur: float = 0.0
    exposure_after_hedge_eur: float = 0.0
    current_coverage_ratio: float = 0.0
    coverage_ratio_after_hedge: float = 0.0
    
    # Validity
    valid_until: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_expired: bool = False
    
    # Policy reference
    policy_id: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "proposal_id": self.proposal_id,
            "trigger_type": self.trigger_type.value,
            "trigger_reason": self.trigger_reason,
            "triggered_at": self.triggered_at,
            "proposed_mode": self.proposed_mode.value,
            "proposed_amount_eur": self.proposed_amount_eur,
            "proposed_exposure_ids": self.proposed_exposure_ids,
            "hypothetical_path": self.hypothetical_path,
            "hypothetical_rate": self.hypothetical_rate,
            "hypothetical_cost_eur": self.hypothetical_cost_eur,
            "current_exposure_eur": self.current_exposure_eur,
            "exposure_after_hedge_eur": self.exposure_after_hedge_eur,
            "current_coverage_ratio": self.current_coverage_ratio,
            "coverage_ratio_after_hedge": self.coverage_ratio_after_hedge,
            "valid_until": self.valid_until,
            "is_expired": self.is_expired,
            "policy_id": self.policy_id
        }


@dataclass
class HedgeEvent:
    """A hedge execution event."""
    hedge_id: str                     # Unique hedge identifier
    status: HedgeStatus               # Current status
    
    # Trigger
    trigger_type: HedgeTriggerType
    trigger_reason: str
    policy_id: Optional[str] = None
    proposal_id: Optional[str] = None  # If originated from proposal
    
    # Execution mode
    mode: HedgeMode = HedgeMode.DEFERRED
    
    # Hedge amounts
    target_amount_eur: float = 0.0    # Target hedge amount
    executed_amount_eur: float = 0.0  # Actually executed
    remaining_amount_eur: float = 0.0 # Remaining to execute
    
    # Covered exposures
    exposure_ids: List[str] = field(default_factory=list)
    exposures_before_eur: float = 0.0
    exposures_after_eur: float = 0.0
    
    # Market execution
    conversion_ids: List[str] = field(default_factory=list)  # Market conversions
    
    # Treasury impact
    treasury_snapshot_before: Optional[str] = None
    treasury_snapshot_after: Optional[str] = None
    coverage_ratio_before: float = 0.0
    coverage_ratio_after: float = 0.0
    
    # Ledger entries
    ledger_entry_ids: List[str] = field(default_factory=list)
    
    # Shadow mode
    is_shadow: bool = True            # Shadow execution (simulated)
    shadow_execution_log: Optional[Dict] = None
    
    # Costs
    total_cost_eur: float = 0.0       # Total hedge cost
    slippage_cost_eur: float = 0.0    # Slippage cost
    fee_cost_eur: float = 0.0         # Trading fees
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # Error handling
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    
    # Batch reference
    batch_id: Optional[str] = None    # If part of batch hedge
    
    def to_dict(self) -> Dict:
        return {
            "hedge_id": self.hedge_id,
            "status": self.status.value,
            "trigger_type": self.trigger_type.value,
            "trigger_reason": self.trigger_reason,
            "policy_id": self.policy_id,
            "proposal_id": self.proposal_id,
            "mode": self.mode.value,
            "target_amount_eur": self.target_amount_eur,
            "executed_amount_eur": self.executed_amount_eur,
            "remaining_amount_eur": self.remaining_amount_eur,
            "exposure_ids": self.exposure_ids,
            "exposures_before_eur": self.exposures_before_eur,
            "exposures_after_eur": self.exposures_after_eur,
            "conversion_ids": self.conversion_ids,
            "treasury_snapshot_before": self.treasury_snapshot_before,
            "treasury_snapshot_after": self.treasury_snapshot_after,
            "coverage_ratio_before": self.coverage_ratio_before,
            "coverage_ratio_after": self.coverage_ratio_after,
            "ledger_entry_ids": self.ledger_entry_ids,
            "is_shadow": self.is_shadow,
            "shadow_execution_log": self.shadow_execution_log,
            "total_cost_eur": self.total_cost_eur,
            "slippage_cost_eur": self.slippage_cost_eur,
            "fee_cost_eur": self.fee_cost_eur,
            "created_at": self.created_at,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "batch_id": self.batch_id
        }

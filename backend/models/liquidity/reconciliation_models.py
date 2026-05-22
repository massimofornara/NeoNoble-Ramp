"""
Reconciliation Models.

Defines data structures for treasury reconciliation:
- Settlement batches
- Reconciliation reports
- Coverage events
"""

from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timezone


class ReconciliationStatus(Enum):
    """Reconciliation batch status."""
    PENDING = "pending"               # Batch created, not processed
    PROCESSING = "processing"         # Currently processing
    COMPLETED = "completed"           # Successfully reconciled
    FAILED = "failed"                 # Reconciliation failed
    MANUAL_REVIEW = "manual_review"   # Requires manual review


@dataclass
class CoverageEvent:
    """A coverage action event."""
    coverage_id: str                  # Unique coverage event ID
    
    # Coverage action type
    action_type: str                  # 'hedge', 'conversion', 'adjustment', 'manual'
    
    # Amounts
    amount_eur: float                 # Coverage amount
    
    # Linked entities
    exposure_id: Optional[str] = None       # Exposure being covered
    hedge_id: Optional[str] = None          # Associated hedge
    conversion_id: Optional[str] = None     # Associated conversion
    ledger_entry_id: Optional[str] = None   # Treasury ledger entry
    
    # Coverage metrics
    exposure_before_eur: float = 0.0
    exposure_after_eur: float = 0.0
    coverage_pct_increase: float = 0.0
    
    # Metadata
    description: str = ""
    provider: str = "internal"        # Coverage provider
    
    # Shadow mode
    is_shadow: bool = True
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "coverage_id": self.coverage_id,
            "action_type": self.action_type,
            "amount_eur": self.amount_eur,
            "exposure_id": self.exposure_id,
            "hedge_id": self.hedge_id,
            "conversion_id": self.conversion_id,
            "ledger_entry_id": self.ledger_entry_id,
            "exposure_before_eur": self.exposure_before_eur,
            "exposure_after_eur": self.exposure_after_eur,
            "coverage_pct_increase": self.coverage_pct_increase,
            "description": self.description,
            "provider": self.provider,
            "is_shadow": self.is_shadow,
            "created_at": self.created_at
        }


@dataclass
class SettlementBatch:
    """A settlement reconciliation batch."""
    batch_id: str                     # Unique batch identifier
    status: ReconciliationStatus
    
    # Time range
    period_start: str                 # Batch period start (UTC)
    period_end: str                   # Batch period end (UTC)
    
    # Transaction counts
    transaction_count: int = 0
    settlement_count: int = 0
    exposure_count: int = 0
    hedge_count: int = 0
    conversion_count: int = 0
    
    # Linked IDs
    quote_ids: List[str] = field(default_factory=list)
    settlement_ids: List[str] = field(default_factory=list)
    exposure_ids: List[str] = field(default_factory=list)
    hedge_ids: List[str] = field(default_factory=list)
    conversion_ids: List[str] = field(default_factory=list)
    ledger_entry_ids: List[str] = field(default_factory=list)
    
    # Volume totals
    total_crypto_inflow: Dict[str, float] = field(default_factory=dict)  # {"NENO": 10.5}
    total_fiat_outflow: Dict[str, float] = field(default_factory=dict)   # {"EUR": 100000}
    total_fees_collected: Dict[str, float] = field(default_factory=dict) # {"EUR": 1500}
    
    # Treasury state
    treasury_snapshot_start: Optional[str] = None
    treasury_snapshot_end: Optional[str] = None
    coverage_ratio_start: float = 0.0
    coverage_ratio_end: float = 0.0
    
    # Exposure metrics
    exposure_created_eur: float = 0.0
    exposure_covered_eur: float = 0.0
    exposure_net_delta_eur: float = 0.0
    
    # Reconciliation checks
    ledger_balanced: bool = False     # Ledger entries balance
    exposure_reconciled: bool = False # Exposures match ledger
    treasury_reconciled: bool = False # Treasury snapshot correct
    
    # Discrepancies
    discrepancies: List[Dict] = field(default_factory=list)
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    processed_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # Error handling
    error_message: Optional[str] = None
    
    # Audit
    checksum: Optional[str] = None    # Batch integrity checksum
    
    def to_dict(self) -> Dict:
        return {
            "batch_id": self.batch_id,
            "status": self.status.value,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "transaction_count": self.transaction_count,
            "settlement_count": self.settlement_count,
            "exposure_count": self.exposure_count,
            "hedge_count": self.hedge_count,
            "conversion_count": self.conversion_count,
            "quote_ids": self.quote_ids,
            "settlement_ids": self.settlement_ids,
            "exposure_ids": self.exposure_ids,
            "hedge_ids": self.hedge_ids,
            "conversion_ids": self.conversion_ids,
            "ledger_entry_ids": self.ledger_entry_ids,
            "total_crypto_inflow": self.total_crypto_inflow,
            "total_fiat_outflow": self.total_fiat_outflow,
            "total_fees_collected": self.total_fees_collected,
            "treasury_snapshot_start": self.treasury_snapshot_start,
            "treasury_snapshot_end": self.treasury_snapshot_end,
            "coverage_ratio_start": self.coverage_ratio_start,
            "coverage_ratio_end": self.coverage_ratio_end,
            "exposure_created_eur": self.exposure_created_eur,
            "exposure_covered_eur": self.exposure_covered_eur,
            "exposure_net_delta_eur": self.exposure_net_delta_eur,
            "ledger_balanced": self.ledger_balanced,
            "exposure_reconciled": self.exposure_reconciled,
            "treasury_reconciled": self.treasury_reconciled,
            "discrepancies": self.discrepancies,
            "created_at": self.created_at,
            "processed_at": self.processed_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
            "checksum": self.checksum
        }


@dataclass
class ReconciliationReport:
    """A reconciliation summary report."""
    report_id: str
    report_type: str                  # 'daily', 'weekly', 'monthly', 'custom'
    
    # Time range
    period_start: str
    period_end: str
    
    # Batches included
    batch_ids: List[str] = field(default_factory=list)
    batch_count: int = 0
    
    # Volume summary
    total_transactions: int = 0
    total_crypto_volume: Dict[str, float] = field(default_factory=dict)
    total_fiat_volume: Dict[str, float] = field(default_factory=dict)
    total_fees: Dict[str, float] = field(default_factory=dict)
    
    # Exposure summary
    total_exposure_created_eur: float = 0.0
    total_exposure_covered_eur: float = 0.0
    net_exposure_change_eur: float = 0.0
    
    # Coverage metrics
    average_coverage_ratio: float = 0.0
    min_coverage_ratio: float = 0.0
    max_coverage_ratio: float = 0.0
    
    # Hedge summary
    total_hedges: int = 0
    total_hedge_amount_eur: float = 0.0
    total_hedge_cost_eur: float = 0.0
    
    # Conversion summary
    total_conversions: int = 0
    total_conversion_amount_eur: float = 0.0
    average_slippage_pct: float = 0.0
    
    # Treasury movement
    treasury_balance_start_eur: float = 0.0
    treasury_balance_end_eur: float = 0.0
    treasury_net_change_eur: float = 0.0
    
    # Reconciliation status
    fully_reconciled: bool = False
    reconciliation_issues: List[Dict] = field(default_factory=list)
    
    # Timestamps
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "report_id": self.report_id,
            "report_type": self.report_type,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "batch_ids": self.batch_ids,
            "batch_count": self.batch_count,
            "total_transactions": self.total_transactions,
            "total_crypto_volume": self.total_crypto_volume,
            "total_fiat_volume": self.total_fiat_volume,
            "total_fees": self.total_fees,
            "total_exposure_created_eur": self.total_exposure_created_eur,
            "total_exposure_covered_eur": self.total_exposure_covered_eur,
            "net_exposure_change_eur": self.net_exposure_change_eur,
            "average_coverage_ratio": self.average_coverage_ratio,
            "min_coverage_ratio": self.min_coverage_ratio,
            "max_coverage_ratio": self.max_coverage_ratio,
            "total_hedges": self.total_hedges,
            "total_hedge_amount_eur": self.total_hedge_amount_eur,
            "total_hedge_cost_eur": self.total_hedge_cost_eur,
            "total_conversions": self.total_conversions,
            "total_conversion_amount_eur": self.total_conversion_amount_eur,
            "average_slippage_pct": self.average_slippage_pct,
            "treasury_balance_start_eur": self.treasury_balance_start_eur,
            "treasury_balance_end_eur": self.treasury_balance_end_eur,
            "treasury_net_change_eur": self.treasury_net_change_eur,
            "fully_reconciled": self.fully_reconciled,
            "reconciliation_issues": self.reconciliation_issues,
            "generated_at": self.generated_at
        }

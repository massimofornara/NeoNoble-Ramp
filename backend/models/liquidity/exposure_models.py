"""
Exposure Record Models.

Defines data structures for tracking treasury exposure:
- Per-transaction exposure records
- Exposure summaries and aggregations
"""

from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timezone


class ExposureType(Enum):
    """Types of treasury exposure."""
    OFFRAMP_PAYOUT = "offramp_payout"         # Fiat payout exposure from off-ramp
    ONRAMP_CRYPTO = "onramp_crypto"           # Crypto delivery exposure from on-ramp
    HEDGE_POSITION = "hedge_position"         # Open hedge position exposure
    PENDING_CONVERSION = "pending_conversion" # Pending market conversion


class ExposureStatus(Enum):
    """Exposure lifecycle status."""
    CREATED = "created"                       # Exposure record created
    ACTIVE = "active"                         # Exposure is active/outstanding
    PARTIALLY_COVERED = "partially_covered"   # Partially hedged/converted
    FULLY_COVERED = "fully_covered"           # Fully hedged/converted
    SETTLED = "settled"                       # Exposure settled via reconciliation
    CANCELLED = "cancelled"                   # Cancelled (e.g., expired quote)


@dataclass
class ExposureRecord:
    """A single exposure record linked to a transaction."""
    exposure_id: str                          # Unique exposure identifier
    exposure_type: ExposureType               # Type of exposure
    status: ExposureStatus                    # Current status
    
    # Transaction linkage
    quote_id: str                             # Associated quote/transaction
    settlement_id: Optional[str] = None       # Associated settlement
    direction: str = "offramp"                # Transaction direction
    
    # Exposure amounts
    crypto_amount: float = 0.0                # Crypto amount (inflow)
    crypto_currency: str = "NENO"             # Crypto currency
    fiat_amount: float = 0.0                  # Fiat amount (outflow)
    fiat_currency: str = "EUR"                # Fiat currency
    
    # Exposure delta (EUR equivalent)
    exposure_delta_eur: float = 0.0           # Net exposure change in EUR
    
    # Exchange rate snapshot
    exchange_rate: float = 0.0                # Rate at exposure creation
    rate_source: str = "internal"             # Rate source (internal, market, etc.)
    
    # Coverage tracking
    covered_amount_eur: float = 0.0           # Amount covered by hedge/conversion
    coverage_percentage: float = 0.0          # Percentage covered
    coverage_events: List[str] = field(default_factory=list)  # Coverage event IDs
    
    # Reconciliation
    batch_id: Optional[str] = None            # Reconciliation batch ID
    reconciled_at: Optional[str] = None       # When reconciled
    
    # On-chain reference (for reconstructability)
    deposit_tx_hash: Optional[str] = None     # On-chain deposit transaction
    deposit_block: Optional[int] = None       # Block number
    
    # Payout reference (for reconstructability)
    payout_provider: Optional[str] = None     # Payout provider (stripe, etc.)
    payout_reference: Optional[str] = None    # Payout provider reference
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    settled_at: Optional[str] = None
    
    # Treasury position snapshot at creation
    treasury_snapshot_id: Optional[str] = None
    treasury_coverage_ratio_at_creation: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "exposure_id": self.exposure_id,
            "exposure_type": self.exposure_type.value,
            "status": self.status.value,
            "quote_id": self.quote_id,
            "settlement_id": self.settlement_id,
            "direction": self.direction,
            "crypto_amount": self.crypto_amount,
            "crypto_currency": self.crypto_currency,
            "fiat_amount": self.fiat_amount,
            "fiat_currency": self.fiat_currency,
            "exposure_delta_eur": self.exposure_delta_eur,
            "exchange_rate": self.exchange_rate,
            "rate_source": self.rate_source,
            "covered_amount_eur": self.covered_amount_eur,
            "coverage_percentage": self.coverage_percentage,
            "coverage_events": self.coverage_events,
            "batch_id": self.batch_id,
            "reconciled_at": self.reconciled_at,
            "deposit_tx_hash": self.deposit_tx_hash,
            "deposit_block": self.deposit_block,
            "payout_provider": self.payout_provider,
            "payout_reference": self.payout_reference,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "settled_at": self.settled_at,
            "treasury_snapshot_id": self.treasury_snapshot_id,
            "treasury_coverage_ratio_at_creation": self.treasury_coverage_ratio_at_creation
        }


@dataclass
class ExposureSummary:
    """Aggregated exposure summary."""
    timestamp: str
    
    # Total exposure by status
    active_exposure_eur: float = 0.0
    pending_coverage_eur: float = 0.0
    fully_covered_eur: float = 0.0
    settled_eur: float = 0.0
    
    # Counts
    active_count: int = 0
    pending_count: int = 0
    covered_count: int = 0
    settled_count: int = 0
    
    # Coverage metrics
    average_coverage_percentage: float = 0.0
    time_to_coverage_avg_hours: float = 0.0
    
    # Risk metrics
    max_single_exposure_eur: float = 0.0
    concentration_ratio: float = 0.0  # Largest / Total
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "active_exposure_eur": self.active_exposure_eur,
            "pending_coverage_eur": self.pending_coverage_eur,
            "fully_covered_eur": self.fully_covered_eur,
            "settled_eur": self.settled_eur,
            "active_count": self.active_count,
            "pending_count": self.pending_count,
            "covered_count": self.covered_count,
            "settled_count": self.settled_count,
            "average_coverage_percentage": self.average_coverage_percentage,
            "time_to_coverage_avg_hours": self.time_to_coverage_avg_hours,
            "max_single_exposure_eur": self.max_single_exposure_eur,
            "concentration_ratio": self.concentration_ratio
        }

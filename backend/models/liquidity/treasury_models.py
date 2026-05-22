"""
Treasury Ledger Models.

Defines data structures for treasury operations including:
- Ledger entries (inflows, outflows, adjustments)
- Treasury snapshots
- Configuration
"""

from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timezone


class LedgerEntryType(Enum):
    """Types of treasury ledger entries."""
    # Inflows
    CRYPTO_INFLOW = "crypto_inflow"           # NENO deposit received
    CRYPTO_CONVERSION = "crypto_conversion"   # Conversion proceeds
    HEDGE_SETTLEMENT = "hedge_settlement"     # Hedge position closed
    TREASURY_DEPOSIT = "treasury_deposit"     # External treasury funding
    
    # Outflows
    FIAT_PAYOUT = "fiat_payout"               # EUR payout to user
    HEDGE_MARGIN = "hedge_margin"             # Hedge position opened
    CONVERSION_COST = "conversion_cost"       # Market conversion fees
    TREASURY_WITHDRAWAL = "treasury_withdrawal"  # Treasury withdrawal
    
    # Adjustments
    EXPOSURE_ADJUSTMENT = "exposure_adjustment"  # Exposure delta correction
    RECONCILIATION_ADJUSTMENT = "reconciliation_adjustment"  # Batch reconciliation
    FEE_ALLOCATION = "fee_allocation"         # Fee revenue allocation
    VIRTUAL_FLOOR_CREDIT = "virtual_floor_credit"  # Virtual liquidity floor


@dataclass
class LedgerEntry:
    """A single treasury ledger entry."""
    entry_id: str                              # Unique entry identifier
    sequence_number: int                       # Monotonic sequence for ordering
    entry_type: LedgerEntryType               # Type of entry
    
    # Amount details
    amount: float                              # Amount (positive for inflow, negative for outflow)
    currency: str                              # Currency code (EUR, NENO, BNB, USDT, etc.)
    amount_eur_equivalent: float               # EUR equivalent at time of entry
    
    # Balance tracking
    balance_before: float                      # Treasury balance before this entry
    balance_after: float                       # Treasury balance after this entry
    
    # Reference linkage
    quote_id: Optional[str] = None            # Associated quote/transaction
    settlement_id: Optional[str] = None       # Associated settlement
    batch_id: Optional[str] = None            # Reconciliation batch
    hedge_id: Optional[str] = None            # Associated hedge event
    conversion_id: Optional[str] = None       # Associated market conversion
    
    # Metadata
    description: str = ""                     # Human-readable description
    provider_reference: Optional[str] = None  # External provider reference
    rate_snapshot: Optional[Dict] = None      # Exchange rates at time of entry
    
    # Timestamps (UTC normalized)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    effective_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Audit
    audit_hash: Optional[str] = None          # Hash for integrity verification
    previous_entry_hash: Optional[str] = None # Chain integrity
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "entry_id": self.entry_id,
            "sequence_number": self.sequence_number,
            "entry_type": self.entry_type.value,
            "amount": self.amount,
            "currency": self.currency,
            "amount_eur_equivalent": self.amount_eur_equivalent,
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
            "quote_id": self.quote_id,
            "settlement_id": self.settlement_id,
            "batch_id": self.batch_id,
            "hedge_id": self.hedge_id,
            "conversion_id": self.conversion_id,
            "description": self.description,
            "provider_reference": self.provider_reference,
            "rate_snapshot": self.rate_snapshot,
            "created_at": self.created_at,
            "effective_at": self.effective_at,
            "audit_hash": self.audit_hash,
            "previous_entry_hash": self.previous_entry_hash
        }


@dataclass
class TreasurySnapshot:
    """Point-in-time treasury state snapshot."""
    snapshot_id: str
    timestamp: str
    
    # Balances by currency
    balances: Dict[str, float]                # {"EUR": 1000000, "NENO": 50, ...}
    
    # EUR-normalized totals
    total_eur_equivalent: float               # Total treasury value in EUR
    virtual_floor_eur: float                  # Virtual floor liquidity
    real_balance_eur: float                   # Real funded balance
    
    # Exposure metrics
    total_exposure_eur: float                 # Outstanding exposure
    coverage_ratio: float                     # (real + virtual) / exposure
    
    # Sequence tracking
    last_sequence_number: int                 # Last ledger sequence included
    last_entry_id: str                        # Last entry ID included
    
    # Verification
    checksum: Optional[str] = None            # Snapshot integrity checksum
    
    def to_dict(self) -> Dict:
        return {
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp,
            "balances": self.balances,
            "total_eur_equivalent": self.total_eur_equivalent,
            "virtual_floor_eur": self.virtual_floor_eur,
            "real_balance_eur": self.real_balance_eur,
            "total_exposure_eur": self.total_exposure_eur,
            "coverage_ratio": self.coverage_ratio,
            "last_sequence_number": self.last_sequence_number,
            "last_entry_id": self.last_entry_id,
            "checksum": self.checksum
        }


@dataclass
class TreasuryConfig:
    """Treasury configuration parameters."""
    # Virtual floor (simulated liquidity)
    virtual_floor_eur: float = 100_000_000.0  # €100M virtual floor
    virtual_floor_enabled: bool = True
    
    # Real balance tracking
    initial_real_balance_eur: float = 0.0
    
    # Coverage thresholds
    min_coverage_ratio: float = 1.0           # Minimum 100% coverage
    target_coverage_ratio: float = 1.5        # Target 150% coverage
    critical_coverage_ratio: float = 0.8      # Critical threshold
    
    # Supported currencies
    supported_currencies: List[str] = field(default_factory=lambda: ["EUR", "NENO", "BNB", "USDT", "USDC"])
    base_currency: str = "EUR"
    
    # Reconciliation settings
    auto_reconciliation_enabled: bool = True
    reconciliation_interval_hours: int = 12
    
    def to_dict(self) -> Dict:
        return {
            "virtual_floor_eur": self.virtual_floor_eur,
            "virtual_floor_enabled": self.virtual_floor_enabled,
            "initial_real_balance_eur": self.initial_real_balance_eur,
            "min_coverage_ratio": self.min_coverage_ratio,
            "target_coverage_ratio": self.target_coverage_ratio,
            "critical_coverage_ratio": self.critical_coverage_ratio,
            "supported_currencies": self.supported_currencies,
            "base_currency": self.base_currency,
            "auto_reconciliation_enabled": self.auto_reconciliation_enabled,
            "reconciliation_interval_hours": self.reconciliation_interval_hours
        }

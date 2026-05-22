"""
Market Routing Models.

Defines data structures for market/CEX routing:
- Venue definitions
- Conversion paths
- Market conversion events
"""

from enum import Enum
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime, timezone


class RoutingVenue(Enum):
    """Supported routing venues."""
    INTERNAL = "internal"           # Internal PoR treasury (no market)
    BINANCE = "binance"             # Binance CEX
    KRAKEN = "kraken"               # Kraken CEX
    OKX = "okx"                     # OKX CEX
    COINBASE = "coinbase"           # Coinbase CEX
    UNISWAP = "uniswap"             # Uniswap DEX
    PANCAKESWAP = "pancakeswap"     # PancakeSwap DEX
    SHADOW = "shadow"               # Shadow mode (simulated)


class RoutingStatus(Enum):
    """Market routing execution status."""
    PROPOSED = "proposed"           # Routing proposed (shadow mode)
    QUEUED = "queued"               # Queued for execution
    EXECUTING = "executing"         # Currently executing
    PARTIAL = "partial"             # Partially filled
    COMPLETED = "completed"         # Fully executed
    FAILED = "failed"               # Execution failed
    CANCELLED = "cancelled"         # Cancelled before execution


@dataclass
class ConversionPath:
    """A conversion path through one or more venues."""
    path_id: str
    
    # Source and destination
    source_currency: str              # e.g., "NENO"
    destination_currency: str         # e.g., "EUR"
    
    # Path steps
    steps: List[Dict] = field(default_factory=list)
    # Example: [{"from": "NENO", "to": "BNB", "venue": "pancakeswap"}, 
    #          {"from": "BNB", "to": "USDT", "venue": "binance"},
    #          {"from": "USDT", "to": "EUR", "venue": "binance"}]
    
    # Estimated rates and costs
    estimated_rate: float = 0.0       # Overall conversion rate
    estimated_slippage_pct: float = 0.0
    estimated_fee_pct: float = 0.0
    estimated_total_cost_pct: float = 0.0
    
    # Path quality metrics
    liquidity_score: float = 0.0      # 0-100 liquidity score
    reliability_score: float = 0.0    # 0-100 reliability score
    execution_time_estimate_seconds: int = 0
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    valid_until: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "path_id": self.path_id,
            "source_currency": self.source_currency,
            "destination_currency": self.destination_currency,
            "steps": self.steps,
            "estimated_rate": self.estimated_rate,
            "estimated_slippage_pct": self.estimated_slippage_pct,
            "estimated_fee_pct": self.estimated_fee_pct,
            "estimated_total_cost_pct": self.estimated_total_cost_pct,
            "liquidity_score": self.liquidity_score,
            "reliability_score": self.reliability_score,
            "execution_time_estimate_seconds": self.execution_time_estimate_seconds,
            "created_at": self.created_at,
            "valid_until": self.valid_until
        }


@dataclass
class MarketConversionEvent:
    """A market conversion execution event."""
    conversion_id: str                # Unique conversion identifier
    status: RoutingStatus             # Execution status
    
    # Conversion details
    source_currency: str              # Source currency
    source_amount: float              # Amount to convert
    destination_currency: str         # Destination currency
    venue: RoutingVenue               # Execution venue
    
    # Amounts with defaults
    destination_amount: float = 0.0   # Amount received
    
    # Routing
    path: Optional[ConversionPath] = None  # Full conversion path
    
    # Execution details
    executed_rate: float = 0.0        # Actual execution rate
    slippage_pct: float = 0.0         # Actual slippage
    fee_amount: float = 0.0           # Fees paid
    fee_currency: str = "EUR"         # Fee currency
    
    # Provider references
    venue_order_id: Optional[str] = None       # Venue order ID
    venue_trade_ids: List[str] = field(default_factory=list)  # Individual trade IDs
    
    # Linkage
    exposure_id: Optional[str] = None          # Associated exposure record
    quote_id: Optional[str] = None             # Associated quote
    hedge_id: Optional[str] = None             # Associated hedge event
    ledger_entry_id: Optional[str] = None      # Treasury ledger entry
    
    # Shadow mode
    is_shadow: bool = True            # Shadow mode (simulated)
    shadow_execution_log: Optional[Dict] = None  # Simulated execution details
    
    # Rate snapshots
    rate_snapshot_before: Optional[Dict] = None  # Market rates before
    rate_snapshot_after: Optional[Dict] = None   # Market rates after
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # Error handling
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "conversion_id": self.conversion_id,
            "status": self.status.value,
            "source_currency": self.source_currency,
            "source_amount": self.source_amount,
            "destination_currency": self.destination_currency,
            "destination_amount": self.destination_amount,
            "venue": self.venue.value,
            "path": self.path.to_dict() if self.path else None,
            "executed_rate": self.executed_rate,
            "slippage_pct": self.slippage_pct,
            "fee_amount": self.fee_amount,
            "fee_currency": self.fee_currency,
            "venue_order_id": self.venue_order_id,
            "venue_trade_ids": self.venue_trade_ids,
            "exposure_id": self.exposure_id,
            "quote_id": self.quote_id,
            "hedge_id": self.hedge_id,
            "ledger_entry_id": self.ledger_entry_id,
            "is_shadow": self.is_shadow,
            "shadow_execution_log": self.shadow_execution_log,
            "rate_snapshot_before": self.rate_snapshot_before,
            "rate_snapshot_after": self.rate_snapshot_after,
            "created_at": self.created_at,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "retry_count": self.retry_count
        }


@dataclass
class RoutingConfig:
    """Market routing configuration."""
    # Mode
    shadow_mode: bool = True          # Shadow mode (no real execution)
    
    # Enabled venues
    enabled_venues: List[RoutingVenue] = field(
        default_factory=lambda: [RoutingVenue.SHADOW]
    )
    primary_venue: RoutingVenue = RoutingVenue.SHADOW
    
    # Default conversion path for NENO
    neno_conversion_path: List[str] = field(
        default_factory=lambda: ["NENO", "BNB", "USDT", "EUR"]
    )
    
    # Execution parameters
    max_slippage_pct: float = 1.0     # Maximum acceptable slippage
    max_retries: int = 3               # Maximum retry attempts
    execution_timeout_seconds: int = 300  # 5 minute timeout
    
    # Best execution settings
    use_best_execution: bool = True   # Enable best-execution routing
    split_large_orders: bool = True   # Split large orders across venues
    large_order_threshold_eur: float = 50000.0  # Threshold for splitting
    
    def to_dict(self) -> Dict:
        return {
            "shadow_mode": self.shadow_mode,
            "enabled_venues": [v.value for v in self.enabled_venues],
            "primary_venue": self.primary_venue.value,
            "neno_conversion_path": self.neno_conversion_path,
            "max_slippage_pct": self.max_slippage_pct,
            "max_retries": self.max_retries,
            "execution_timeout_seconds": self.execution_timeout_seconds,
            "use_best_execution": self.use_best_execution,
            "split_large_orders": self.split_large_orders,
            "large_order_threshold_eur": self.large_order_threshold_eur
        }

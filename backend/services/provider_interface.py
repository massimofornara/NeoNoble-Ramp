"""
Provider Interface - Abstract base for off-ramp liquidity providers.

Supports multiple provider backends:
- InternalPoRProvider (default, autonomous)
- TransakProvider (future)
- MoonPayProvider (future)
- RampProvider (future)
- BanxaProvider (future)
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple, List
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


class ProviderType(str, Enum):
    """Supported provider types."""
    INTERNAL_POR = "internal_por"
    TRANSAK = "transak"
    MOONPAY = "moonpay"
    RAMP = "ramp"
    BANXA = "banxa"


class TransactionState(str, Enum):
    """Enterprise-grade transaction lifecycle states."""
    # Quote phase
    QUOTE_CREATED = "QUOTE_CREATED"
    QUOTE_ACCEPTED = "QUOTE_ACCEPTED"
    QUOTE_EXPIRED = "QUOTE_EXPIRED"
    QUOTE_CANCELLED = "QUOTE_CANCELLED"
    
    # Off-Ramp: Deposit phase (Crypto → Fiat)
    DEPOSIT_PENDING = "DEPOSIT_PENDING"
    DEPOSIT_DETECTED = "DEPOSIT_DETECTED"
    DEPOSIT_CONFIRMED = "DEPOSIT_CONFIRMED"
    DEPOSIT_FAILED = "DEPOSIT_FAILED"
    
    # On-Ramp: Payment phase (Fiat → Crypto)
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_DETECTED = "PAYMENT_DETECTED"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    
    # On-Ramp: Crypto delivery phase
    CRYPTO_SENDING = "CRYPTO_SENDING"
    CRYPTO_SENT = "CRYPTO_SENT"
    CRYPTO_CONFIRMED = "CRYPTO_CONFIRMED"
    CRYPTO_FAILED = "CRYPTO_FAILED"
    
    # Off-Ramp: Settlement phase
    SETTLEMENT_PENDING = "SETTLEMENT_PENDING"
    SETTLEMENT_PROCESSING = "SETTLEMENT_PROCESSING"
    SETTLEMENT_COMPLETED = "SETTLEMENT_COMPLETED"
    SETTLEMENT_FAILED = "SETTLEMENT_FAILED"
    
    # C-SAFE DEX Conversion phase (Real market conversion)
    LIQUIDITY_PENDING = "LIQUIDITY_PENDING"
    CONVERSION_IN_PROGRESS = "CONVERSION_IN_PROGRESS"
    CONVERSION_BATCH_EXECUTING = "CONVERSION_BATCH_EXECUTING"
    CONVERSION_PAUSED = "CONVERSION_PAUSED"
    CONVERSION_COMPLETED = "CONVERSION_COMPLETED"
    CONVERSION_FAILED = "CONVERSION_FAILED"
    SETTLEMENT_READY = "SETTLEMENT_READY"
    
    # Off-Ramp: Payout phase
    PAYOUT_INITIATED = "PAYOUT_INITIATED"
    PAYOUT_PROCESSING = "PAYOUT_PROCESSING"
    PAYOUT_EXECUTING = "PAYOUT_EXECUTING"
    PAYOUT_COMPLETED = "PAYOUT_COMPLETED"
    PAYOUT_FAILED = "PAYOUT_FAILED"
    
    # Final states
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class SettlementMode(str, Enum):
    """Settlement timing modes."""
    INSTANT = "instant"  # Immediate completion
    SIMULATED_DELAY = "simulated_delay"  # Realistic 1-3 day delay
    BATCH = "batch"  # Scheduled batch processing


class KYCStatus(str, Enum):
    """KYC verification status."""
    NOT_REQUIRED = "not_required"  # PoR handles KYC
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AMLStatus(str, Enum):
    """AML screening status."""
    NOT_REQUIRED = "not_required"  # PoR handles AML
    PENDING = "pending"
    CLEARED = "cleared"
    FLAGGED = "flagged"
    BLOCKED = "blocked"


@dataclass
class ProviderConfig:
    """Provider configuration."""
    provider_type: ProviderType
    name: str
    enabled: bool = True
    settlement_mode: SettlementMode = SettlementMode.INSTANT
    fee_percentage: float = 1.5
    min_amount_eur: float = 10.0
    max_amount_eur: float = 100_000_000.0  # 100M EUR
    supported_currencies: List[str] = field(default_factory=lambda: ["EUR"])
    supported_cryptos: List[str] = field(default_factory=lambda: ["NENO", "BTC", "ETH"])
    kyc_required: bool = False  # PoR handles KYC
    aml_required: bool = False  # PoR handles AML


@dataclass
class TimelineEvent:
    """Transaction timeline event."""
    timestamp: str
    state: TransactionState
    message: str
    details: Optional[Dict] = None
    provider: str = "internal_por"


@dataclass
class ComplianceInfo:
    """KYC/AML compliance information."""
    kyc_status: KYCStatus = KYCStatus.NOT_REQUIRED
    kyc_provider: str = "internal_por"  # PoR handles KYC responsibility
    kyc_verified_at: Optional[str] = None
    aml_status: AMLStatus = AMLStatus.NOT_REQUIRED
    aml_provider: str = "internal_por"  # PoR handles AML responsibility
    aml_cleared_at: Optional[str] = None
    risk_score: Optional[float] = None
    risk_level: str = "low"  # low, medium, high
    por_responsible: bool = True  # PoR is Merchant-of-Record


@dataclass
class ProviderQuote:
    """Quote from a provider."""
    quote_id: str
    provider: ProviderType
    crypto_amount: float
    crypto_currency: str
    fiat_amount: float
    fiat_currency: str
    exchange_rate: float
    fee_amount: float
    fee_percentage: float
    net_payout: float
    deposit_address: Optional[str]  # For off-ramp: crypto deposit address
    expires_at: str
    created_at: str
    state: TransactionState = TransactionState.QUOTE_CREATED
    compliance: ComplianceInfo = field(default_factory=ComplianceInfo)
    timeline: List[TimelineEvent] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    # On-ramp specific fields
    direction: str = "offramp"  # "onramp" or "offramp"
    wallet_address: Optional[str] = None  # For on-ramp: user's crypto wallet
    payment_reference: Optional[str] = None  # For on-ramp: fiat payment reference
    payment_amount: Optional[float] = None  # For on-ramp: total fiat to pay


@dataclass
class SettlementResult:
    """Settlement execution result."""
    success: bool
    settlement_id: Optional[str] = None
    payout_reference: Optional[str] = None
    state: TransactionState = TransactionState.SETTLEMENT_PENDING
    error: Optional[str] = None
    details: Dict = field(default_factory=dict)


class BaseProvider(ABC):
    """
    Abstract base class for off-ramp providers.
    
    All providers must implement these methods to ensure
    consistent behavior across the platform.
    """
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.logger = logging.getLogger(f"provider.{config.provider_type.value}")
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the provider."""
        pass
    
    @abstractmethod
    async def create_quote(
        self,
        crypto_amount: float,
        crypto_currency: str,
        fiat_currency: str = "EUR",
        user_id: Optional[str] = None,
        bank_account: Optional[str] = None
    ) -> Tuple[Optional[ProviderQuote], Optional[str]]:
        """Create an off-ramp quote."""
        pass
    
    @abstractmethod
    async def accept_quote(
        self,
        quote_id: str,
        bank_account: str
    ) -> Tuple[Optional[ProviderQuote], Optional[str]]:
        """Accept a quote and initiate the off-ramp."""
        pass
    
    @abstractmethod
    async def process_deposit(
        self,
        quote_id: str,
        tx_hash: str,
        amount: float
    ) -> Tuple[Optional[ProviderQuote], Optional[str]]:
        """Process a detected deposit."""
        pass
    
    @abstractmethod
    async def execute_settlement(
        self,
        quote_id: str
    ) -> Tuple[Optional[SettlementResult], Optional[str]]:
        """Execute settlement and payout."""
        pass
    
    @abstractmethod
    async def get_transaction(
        self,
        quote_id: str
    ) -> Optional[ProviderQuote]:
        """Get transaction details."""
        pass
    
    @abstractmethod
    async def get_timeline(
        self,
        quote_id: str
    ) -> List[TimelineEvent]:
        """Get transaction timeline."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available."""
        pass
    
    def get_config(self) -> ProviderConfig:
        """Get provider configuration."""
        return self.config

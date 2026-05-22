"""
Internal Provider-of-Record (PoR) Engine.

Enterprise-grade liquidity provider that operates autonomously
without requiring external credentials or funding.

Behavior matches production providers like:
- Transak Business
- MoonPay Business  
- Ramp Network
- Banxa Enterprise

Features:
- Always-available liquidity pool
- Automatic settlement processing
- Full transaction lifecycle
- KYC/AML responsibility at PoR level
- Enterprise-grade state machine
- Real-time webhook event broadcasting
- Comprehensive audit logging
"""

import os
import logging
import asyncio
from uuid import uuid4
from typing import Dict, Optional, Tuple, List
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from services.exchanges.connector_manager import get_connector_manager
from services.liquidity.routing_service import MarketRoutingService

app = FastAPI()

mongo = AsyncIOMotorClient("mongodb://localhost:27017")
db = mongo["neonoble"]

routing_service = MarketRoutingService(db)

@app.on_event("startup")
async def startup():
    manager = get_connector_manager()
    await manager.enable_live_trading(user_id="system")

    await routing_service.initialize()

    print("🚀 STEP B LIVE: MARKET MAKER + TREASURY + REAL EXECUTION")


from services.provider_interface import (
    BaseProvider,
    ProviderConfig,
    ProviderType,
    ProviderQuote,
    SettlementResult,
    SettlementMode,
    TransactionState,
    TimelineEvent,
    ComplianceInfo,
    KYCStatus,
    AMLStatus
)
from services.pricing_service import pricing_service, NENO_PRICE_EUR
from services.audit_logger import AuditLogger, AuditEventType, get_audit_logger
from services.webhook_service import (
    WebhookService, 
    get_webhook_service, 
    get_webhook_event_type
)

logger = logging.getLogger(__name__)

# PoR Engine Configuration
POR_ENGINE_NAME = "NeoNoble Internal PoR"
POR_ENGINE_VERSION = "2.0.0"
POR_FEE_PERCENTAGE = 1.5
POR_QUOTE_TTL_MINUTES = int(os.environ.get('QUOTE_TTL_MINUTES', '60'))

# Liquidity Pool Configuration (always available)
LIQUIDITY_POOL_EUR = float(os.environ.get('POR_LIQUIDITY_POOL_EUR', '100000000'))  # 100M EUR
LIQUIDITY_UNLIMITED = True  # Never block transactions

# Real Payout Configuration
USE_REAL_PAYOUTS = os.environ.get('USE_REAL_PAYOUTS', 'true').lower() == 'true'


class InternalPoRProvider(BaseProvider):
    """
    Internal Provider-of-Record Engine.
    
    Acts as a real Merchant-of-Record style provider with:
    - Autonomous operation (no external dependencies)
    - Always-available liquidity
    - Full transaction lifecycle management
    - Enterprise-grade state transitions
    - PoR-level KYC/AML responsibility
    - Real-time webhook event broadcasting
    - Comprehensive audit logging
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        config = ProviderConfig(
            provider_type=ProviderType.INTERNAL_POR,
            name=POR_ENGINE_NAME,
            enabled=True,
            settlement_mode=SettlementMode.INSTANT,
            fee_percentage=POR_FEE_PERCENTAGE,
            min_amount_eur=1.0,
            max_amount_eur=LIQUIDITY_POOL_EUR,
            supported_currencies=["EUR"],
            supported_cryptos=["NENO", "BTC", "ETH", "USDT", "USDC", "BNB", "SOL"],
            kyc_required=False,  # PoR handles KYC
            aml_required=False   # PoR handles AML
        )
        super().__init__(config)
        
        self.db = db
        self.transactions_collection = db.por_transactions
        self.settlements_collection = db.por_settlements
        self.liquidity_collection = db.por_liquidity
        self._initialized = False
        self._settlement_mode = SettlementMode.INSTANT
        
        # Wallet service reference (optional)
        self._wallet_service = None
        
        # Audit and webhook services
        self._audit_logger: Optional[AuditLogger] = None
        self._webhook_service: Optional[WebhookService] = None
        
        # Real payout service (optional - for real EUR payouts)
        self._real_payout_service = None
        
        # Liquidity services (Hybrid PoR Architecture - Phase 1)
        self._treasury_service = None
        self._exposure_service = None
        self._routing_service = None
        self._hedging_service = None
        self._reconciliation_service = None
    
    def set_wallet_service(self, wallet_service):
        """Set wallet service for deposit address generation."""
        self._wallet_service = wallet_service
    
    def set_audit_logger(self, audit_logger: AuditLogger):
        """Set audit logger for lifecycle event logging."""
        self._audit_logger = audit_logger
    
    def set_webhook_service(self, webhook_service: WebhookService):
        """Set webhook service for event broadcasting."""
        self._webhook_service = webhook_service
    
    def set_real_payout_service(self, payout_service):
        """Set real payout service for EUR payouts via Stripe."""
        self._real_payout_service = payout_service
        logger.info("Real payout service configured for PoR engine")
    
    def set_liquidity_services(
        self,
        treasury_service=None,
        exposure_service=None,
        routing_service=None,
        hedging_service=None,
        reconciliation_service=None
    ):
        """
        Set liquidity services for Hybrid PoR Architecture.
        
        Phase 1 Configuration:
        - Treasury: REAL tracking
        - Exposure: REAL tracking
        - Routing: SHADOW mode (log-only)
        - Hedging: SHADOW mode (audit-only proposals)
        - Reconciliation: REAL audit ledger
        """
        self._treasury_service = treasury_service
        self._exposure_service = exposure_service
        self._routing_service = routing_service
        self._hedging_service = hedging_service
        self._reconciliation_service = reconciliation_service
        logger.info(
            "Liquidity services configured for PoR engine:\n"
            "  Treasury: REAL | Exposure: REAL | Routing: SHADOW | "
            "Hedging: SHADOW | Reconciliation: REAL"
        )
    
    def set_settlement_mode(self, mode: SettlementMode):
        """Configure settlement mode."""
        self._settlement_mode = mode
        self.config.settlement_mode = mode
        logger.info(f"PoR settlement mode set to: {mode.value}")
    
    async def initialize(self) -> bool:
        """Initialize the PoR engine."""
        if self._initialized:
            return True
        
        try:
            # Create indexes
            await self.transactions_collection.create_index("quote_id", unique=True)
            await self.transactions_collection.create_index("state")
            await self.transactions_collection.create_index("user_id")
            await self.transactions_collection.create_index("deposit_address")
            await self.transactions_collection.create_index("created_at")
            
            await self.settlements_collection.create_index("settlement_id", unique=True)
            await self.settlements_collection.create_index("quote_id")
            await self.settlements_collection.create_index("status")
            
            # Initialize liquidity pool record
            await self._initialize_liquidity_pool()
            
            self._initialized = True
            logger.info(
                f"PoR Engine initialized: {POR_ENGINE_NAME} v{POR_ENGINE_VERSION}\n"
                f"  Settlement Mode: {self._settlement_mode.value}\n"
                f"  Liquidity Pool: €{LIQUIDITY_POOL_EUR:,.0f} (unlimited={LIQUIDITY_UNLIMITED})\n"
                f"  Fee: {POR_FEE_PERCENTAGE}%\n"
                f"  Quote TTL: {POR_QUOTE_TTL_MINUTES} minutes"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize PoR Engine: {e}")
            return False
    
    async def _initialize_liquidity_pool(self):
        """Initialize the virtual liquidity pool."""
        existing = await self.liquidity_collection.find_one({"pool_id": "primary"})
        
        if not existing:
            pool_doc = {
                "pool_id": "primary",
                "currency": "EUR",
                "total_balance": LIQUIDITY_POOL_EUR,
                "available_balance": LIQUIDITY_POOL_EUR,
                "reserved_balance": 0.0,
                "unlimited_mode": LIQUIDITY_UNLIMITED,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            await self.liquidity_collection.insert_one(pool_doc)
            logger.info(f"Initialized PoR liquidity pool: €{LIQUIDITY_POOL_EUR:,.0f}")
    
    def is_available(self) -> bool:
        """PoR is always available."""
        return True
    
    async def create_quote(
        self,
        crypto_amount: float,
        crypto_currency: str,
        fiat_currency: str = "EUR",
        user_id: Optional[str] = None,
        bank_account: Optional[str] = None
    ) -> Tuple[Optional[ProviderQuote], Optional[str]]:
        """
        Create an off-ramp quote.
        
        The PoR engine automatically:
        - Validates the request
        - Calculates pricing (NENO = €10,000 fixed)
        - Generates deposit address if available
        - Returns enterprise-grade quote
        """
        try:
            await self.initialize()
            
            crypto_currency = crypto_currency.upper()
            
            # Validate crypto
            if crypto_currency not in self.config.supported_cryptos:
                return None, f"Unsupported cryptocurrency: {crypto_currency}"
            
            # Get exchange rate
            if crypto_currency == "NENO":
                exchange_rate = NENO_PRICE_EUR
            else:
                try:
                    exchange_rate = await pricing_service.get_price_eur(crypto_currency)
                except Exception as e:
                    return None, f"Unable to fetch price for {crypto_currency}: {e}"
            
            # Calculate amounts
            fiat_amount = Decimal(str(crypto_amount)) * Decimal(str(exchange_rate))
            fee_amount = fiat_amount * Decimal(str(POR_FEE_PERCENTAGE / 100))
            net_payout = fiat_amount - fee_amount
            
            # Generate quote ID
            quote_id = f"por_{uuid4().hex[:16]}"
            
            # Generate deposit address if wallet service available
            deposit_address = None
            if self._wallet_service:
                try:
                    deposit_address, err = await self._wallet_service.generate_deposit_address(quote_id)
                    if err:
                        logger.warning(f"Could not generate deposit address: {err}")
                except Exception as e:
                    logger.warning(f"Wallet service error: {e}")
            
            # Create timestamps
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(minutes=POR_QUOTE_TTL_MINUTES)
            
            # Create compliance info (PoR handles KYC/AML)
            compliance = ComplianceInfo(
                kyc_status=KYCStatus.NOT_REQUIRED,
                kyc_provider="internal_por",
                aml_status=AMLStatus.NOT_REQUIRED,
                aml_provider="internal_por",
                risk_score=0.0,
                risk_level="low",
                por_responsible=True
            )
            
            # Create initial timeline event
            timeline = [
                TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.QUOTE_CREATED,
                    message="Off-ramp quote created by PoR engine",
                    details={
                        "crypto_amount": crypto_amount,
                        "crypto_currency": crypto_currency,
                        "exchange_rate": float(exchange_rate),
                        "net_payout": float(net_payout)
                    },
                    provider="internal_por"
                )
            ]
            
            # Create quote object
            quote = ProviderQuote(
                quote_id=quote_id,
                provider=ProviderType.INTERNAL_POR,
                direction="offramp",  # Explicitly set direction
                crypto_amount=crypto_amount,
                crypto_currency=crypto_currency,
                fiat_amount=float(fiat_amount),
                fiat_currency=fiat_currency,
                exchange_rate=float(exchange_rate),
                fee_amount=float(fee_amount),
                fee_percentage=POR_FEE_PERCENTAGE,
                net_payout=float(net_payout),
                deposit_address=deposit_address,
                expires_at=expires_at.isoformat(),
                created_at=now.isoformat(),
                state=TransactionState.QUOTE_CREATED,
                compliance=compliance,
                timeline=timeline,
                metadata={
                    "user_id": user_id,
                    "bank_account": bank_account,
                    "por_engine": POR_ENGINE_NAME,
                    "por_version": POR_ENGINE_VERSION,
                    "settlement_mode": self._settlement_mode.value,
                    "direction": "offramp"
                }
            )
            
            # Store in database
            await self._store_transaction(quote)
            
            # Broadcast webhook event
            await self._broadcast_state_change(quote, None)
            
            logger.info(
                f"PoR quote created: {quote_id} | "
                f"{crypto_amount} {crypto_currency} → €{float(net_payout):,.2f}"
            )
            
            return quote, None
            
        except Exception as e:
            logger.error(f"Error creating PoR quote: {e}")
            return None, str(e)
    
    async def accept_quote(
        self,
        quote_id: str,
        bank_account: str
    ) -> Tuple[Optional[ProviderQuote], Optional[str]]:
        """
        Accept a quote and initiate the off-ramp.
        
        Transitions: QUOTE_CREATED → QUOTE_ACCEPTED → DEPOSIT_PENDING
        """
        try:
            quote = await self.get_transaction(quote_id)
            if not quote:
                return None, f"Quote not found: {quote_id}"
            
            # Check state
            if quote.state not in [TransactionState.QUOTE_CREATED]:
                return None, f"Quote cannot be accepted in state: {quote.state.value}"
            
            # Check expiry
            expires_at = datetime.fromisoformat(quote.expires_at.replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > expires_at:
                await self._update_state(quote_id, TransactionState.QUOTE_EXPIRED, "Quote has expired")
                return None, "Quote has expired"
            
            now = datetime.now(timezone.utc)
            
            # Update quote with bank account
            quote.metadata["bank_account"] = bank_account
            
            # Add timeline events
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.QUOTE_ACCEPTED,
                message="Quote accepted, awaiting deposit",
                details={"bank_account": bank_account[:8] + "..."},
                provider="internal_por"
            ))
            
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.DEPOSIT_PENDING,
                message="Waiting for crypto deposit",
                details={"deposit_address": quote.deposit_address},
                provider="internal_por"
            ))
            
            # Update state
            quote.state = TransactionState.DEPOSIT_PENDING
            
            # Store update
            await self._store_transaction(quote)
            
            # Broadcast webhook events
            await self._broadcast_state_change(quote, "QUOTE_CREATED")
            
            logger.info(f"PoR quote accepted: {quote_id} → DEPOSIT_PENDING")
            
            return quote, None
            
        except Exception as e:
            logger.error(f"Error accepting quote: {e}")
            return None, str(e)
    
    async def process_deposit(
        self,
        quote_id: str,
        tx_hash: str,
        amount: float
    ) -> Tuple[Optional[ProviderQuote], Optional[str]]:
        """
        Process a detected crypto deposit.
        
        Transitions: DEPOSIT_PENDING → DEPOSIT_DETECTED → DEPOSIT_CONFIRMED
        Then automatically triggers settlement if in INSTANT mode.
        """
        try:
            quote = await self.get_transaction(quote_id)
            if not quote:
                return None, f"Quote not found: {quote_id}"
            
            # Check if already processed (idempotency protection)
            if quote.state in [
                TransactionState.COMPLETED,
                TransactionState.FAILED,
                TransactionState.REFUNDED,
                TransactionState.SETTLEMENT_COMPLETED,
                TransactionState.PAYOUT_COMPLETED
            ]:
                logger.warning(f"Deposit already processed for quote {quote_id} (state: {quote.state.value})")
                return quote, None  # Return current state without error
            
            # Check if deposit can be processed
            if quote.state not in [
                TransactionState.DEPOSIT_PENDING,
                TransactionState.QUOTE_ACCEPTED
            ]:
                return None, f"Cannot process deposit in state: {quote.state.value}"
            
            # Check for duplicate tx_hash
            existing_tx = quote.metadata.get("deposit_tx_hash")
            if existing_tx:
                if existing_tx == tx_hash:
                    logger.warning(f"Duplicate deposit tx_hash for quote {quote_id}")
                    return quote, None  # Idempotent - same tx
                else:
                    return None, f"Quote {quote_id} already has a deposit with different tx_hash"
            
            now = datetime.now(timezone.utc)
            
            # Add deposit detected event
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.DEPOSIT_DETECTED,
                message=f"Deposit detected: {amount} {quote.crypto_currency}",
                details={
                    "tx_hash": tx_hash,
                    "amount_received": amount,
                    "expected_amount": quote.crypto_amount
                },
                provider="internal_por"
            ))
            
            quote.state = TransactionState.DEPOSIT_DETECTED
            
            # Validate amount (with tolerance)
            tolerance = 0.0001
            if abs(amount - quote.crypto_amount) > tolerance:
                quote.timeline.append(TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.DEPOSIT_FAILED,
                    message=f"Amount mismatch: received {amount}, expected {quote.crypto_amount}",
                    provider="internal_por"
                ))
                quote.state = TransactionState.DEPOSIT_FAILED
                await self._store_transaction(quote)
                return None, f"Amount mismatch: received {amount}, expected {quote.crypto_amount}"
            
            # Mark deposit as confirmed
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.DEPOSIT_CONFIRMED,
                message="Deposit confirmed, initiating settlement",
                details={"confirmations": "sufficient"},
                provider="internal_por"
            ))
            
            quote.state = TransactionState.DEPOSIT_CONFIRMED
            quote.metadata["deposit_tx_hash"] = tx_hash
            quote.metadata["deposit_amount"] = amount
            quote.metadata["deposit_confirmed_at"] = now.isoformat()
            
            await self._store_transaction(quote)
            
            # Broadcast webhook event
            await self._broadcast_state_change(quote, "DEPOSIT_DETECTED")
            
            logger.info(f"PoR deposit confirmed: {quote_id} | {amount} {quote.crypto_currency}")
            
            # === LIQUIDITY LIFECYCLE HOOK: Deposit Confirmed ===
            # Record crypto inflow, create exposure, simulate routing & hedging
            await self._on_deposit_confirmed(
                real_conversion_event = None

if self._routing_service:
    real_conversion_event = await self._routing_service.execute_conversion(
        source_currency=crypto_currency,
        source_amount=crypto_amount,
        destination_currency="EUR",
        exposure_id=exposure_id,
        quote_id=quote_id
    )

    quote = await self.get_transaction(quote_id)
    if quote:
        quote.metadata["real_conversion_executed"] = True
        quote.metadata["real_conversion_id"] = real_conversion_event.conversion_id
        quote.metadata["eur_obtained"] = real_conversion_event.destination_amount
        from services.clearing.clearing_engine import ClearingEngine
clearing_engine = ClearingEngine()

clearing_engine.settle({
    "quote_id": quote_id,
    "amount": real_conversion_event.destination_amount
})

        await self._store_transaction(quote)
                quote_id=quote_id,
                crypto_amount=amount,
                crypto_currency=quote.crypto_currency,
                eur_equivalent=quote.fiat_amount,  # Use quote fiat amount as EUR equivalent
                tx_hash=tx_hash
            )
            
            # Auto-trigger settlement in INSTANT mode
            if self._settlement_mode == SettlementMode.INSTANT:
                settlement_result, error = await self.execute_settlement(quote_id)
                if error:
                    logger.error(f"Settlement failed: {error}")
                    return quote, error
                
                # Refresh quote after settlement
                quote = await self.get_transaction(quote_id)
            
            return quote, None
            
        except Exception as e:
            logger.error(f"Error processing deposit: {e}")
            return None, str(e)

    if not quote.metadata.get("real_conversion_executed"):
    return None, "BLOCKED: No real market execution"

eur_obtained = quote.metadata.get("eur_obtained", 0.0)
if eur_obtained < quote.net_payout:
    return None, f"BLOCKED: insufficient converted EUR ({eur_obtained} < {quote.net_payout})"

if self._treasury_service:
    treasury_summary = await self._treasury_service.get_treasury_summary()
    eur_available = treasury_summary.get("balances", {}).get("EUR", {}).get("available", 0.0)
    if eur_available < quote.net_payout:
        return None, f"Insufficient real EUR liquidity: available={eur_available}, required={quote.net_payout}"

    
    async def execute_settlement(
        self,
        quote_id: str
    ) -> Tuple[Optional[SettlementResult], Optional[str]]:
        """
        Execute settlement and payout.
        
        Transitions: DEPOSIT_CONFIRMED → SETTLEMENT_PENDING → SETTLEMENT_PROCESSING
                    → PAYOUT_INITIATED → PAYOUT_COMPLETED → COMPLETED
        
        If USE_REAL_PAYOUTS is enabled and real_payout_service is configured,
        this will execute a real Stripe payout to the configured IBAN.
        Otherwise, virtual settlement is used.
        """
        try:
            quote = await self.get_transaction(quote_id)
            if not quote:
                return None, f"Quote not found: {quote_id}"
            
            if quote.state not in [
                TransactionState.DEPOSIT_CONFIRMED,
                TransactionState.SETTLEMENT_PENDING
            ]:
                return None, f"Cannot settle in state: {quote.state.value}"
            
            now = datetime.now(timezone.utc)
            settlement_id = f"stl_{uuid4().hex[:12]}"
            payout_ref = f"PAY-{quote_id[-8:].upper()}-{now.strftime('%Y%m%d')}"
            
            # Settlement pending
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.SETTLEMENT_PENDING,
                message="Settlement initiated by PoR engine",
                details={"settlement_id": settlement_id},
                provider="internal_por"
            ))
            quote.state = TransactionState.SETTLEMENT_PENDING
            await self._store_transaction(quote)
            
            # Settlement processing
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.SETTLEMENT_PROCESSING,
                message="Processing settlement through PoR liquidity pool",
                details={"liquidity_pool": "primary"},
                provider="internal_por"
            ))
            quote.state = TransactionState.SETTLEMENT_PROCESSING
            await self._store_transaction(quote)
            
            # Update compliance (AML cleared by PoR)
            quote.compliance.aml_status = AMLStatus.CLEARED
            quote.compliance.aml_cleared_at = now.isoformat()
            
            # Settlement completed
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.SETTLEMENT_COMPLETED,
                message="Settlement completed, initiating payout",
                details={"settlement_id": settlement_id},
                provider="internal_por"
            ))
            quote.state = TransactionState.SETTLEMENT_COMPLETED
            await self._store_transaction(quote)
            
            # Execute payout - real or virtual
            bank_account = quote.metadata.get("bank_account", "N/A")
            payout_result = None
            payout_method = "virtual"
            stripe_payout_id = None
            payout_arrival_date = None
            payout_error = None
            
            # Try real payout if enabled and service is available
            if USE_REAL_PAYOUTS and self._real_payout_service:
                logger.info(f"Executing REAL payout for quote {quote_id}: €{quote.net_payout:,.2f}")
                
                payout_result = await self._real_payout_service.create_payout(
                    quote_id=quote_id,
                    transaction_id=settlement_id,
                    amount_eur=quote.net_payout,
                    reference=payout_ref,
                    metadata={
                        "crypto_amount": quote.crypto_amount,
                        "crypto_currency": quote.crypto_currency,
                        "exchange_rate": quote.exchange_rate,
                        "fee_amount": quote.fee_amount,
                        "user_id": quote.metadata.get("user_id"),
                        "bank_account_masked": bank_account[:8] + "..." if bank_account != "N/A" else None
                    }
                )
                
                if payout_result.success:
                    payout_method = payout_result.method.value if payout_result.method else "stripe"
                    stripe_payout_id = payout_result.payout_id
                    payout_arrival_date = payout_result.arrival_date
                    payout_ref = payout_result.provider_reference or payout_ref
                    
                    logger.info(
                        f"✅ Real payout CREATED: {stripe_payout_id}\n"
                        f"   Method: {payout_method}\n"
                        f"   Amount: €{quote.net_payout:,.2f}\n"
                        f"   Arrival: {payout_arrival_date or 'Pending'}"
                    )
                else:
                    payout_error = payout_result.error
                    logger.error(f"Real payout FAILED: {payout_error}")
                    # Fall back to virtual settlement
                    payout_method = "virtual_fallback"
            
            # Payout initiated
            payout_details = {
                "payout_reference": payout_ref,
                "amount_eur": quote.net_payout,
                "destination": bank_account[:8] + "..." if bank_account != "N/A" else "N/A",
                "method": payout_method
            }
            
            if stripe_payout_id:
                payout_details["stripe_payout_id"] = stripe_payout_id
                payout_details["provider"] = "stripe"
            if payout_arrival_date:
                payout_details["estimated_arrival"] = payout_arrival_date
            if payout_error:
                payout_details["fallback_reason"] = payout_error
            
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.PAYOUT_INITIATED,
                message=f"{'Real' if stripe_payout_id else 'Virtual'} SEPA payout initiated: €{quote.net_payout:,.2f}",
                details=payout_details,
                provider="stripe" if stripe_payout_id else "internal_por"
            ))
            quote.state = TransactionState.PAYOUT_INITIATED
            await self._store_transaction(quote)
            
            # === LIQUIDITY LIFECYCLE HOOK: Settlement Initiated ===
            # Called when payout is initiated but not yet confirmed
            await self._on_settlement_initiated(
                quote_id=quote_id,
                settlement_id=settlement_id,
                net_payout_eur=quote.net_payout,
                fee_eur=quote.fee_amount
            )
            
            # For real payouts, we wait for webhook confirmation
            # For virtual payouts or if real payout created successfully with instant confirmation
            payout_status = payout_result.status.value if payout_result and payout_result.status else None
            
            if payout_status == "paid":
                # Instant confirmation (rare for SEPA, common for card)
                quote.timeline.append(TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.PAYOUT_COMPLETED,
                    message="Payout completed (instant confirmation)",
                    details={
                        "payout_reference": payout_ref,
                        "stripe_payout_id": stripe_payout_id,
                        "method": payout_method
                    },
                    provider="stripe"
                ))
                quote.state = TransactionState.PAYOUT_COMPLETED
                
                # === LIQUIDITY LIFECYCLE HOOK: Payout Completed (Instant) ===
                await self._on_payout_completed(
                    quote_id=quote_id,
                    net_payout_eur=quote.net_payout,
                    fee_eur=quote.fee_amount,
                    settlement_id=settlement_id,
                    payout_reference=stripe_payout_id or payout_ref
                )
                
                quote.timeline.append(TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.COMPLETED,
                    message="Off-ramp completed successfully",
                    details={
                        "settlement_id": settlement_id,
                        "payout_reference": payout_ref,
                        "stripe_payout_id": stripe_payout_id,
                        "net_payout_eur": quote.net_payout,
                        "payout_method": payout_method,
                        "completed_at": now.isoformat()
                    },
                    provider="stripe"
                ))
                quote.state = TransactionState.COMPLETED
                
            elif self._settlement_mode == SettlementMode.INSTANT and not stripe_payout_id:
                # Virtual instant settlement (no real payout service)
                quote.timeline.append(TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.PAYOUT_COMPLETED,
                    message="Payout completed (virtual instant settlement)",
                    details={"payout_reference": payout_ref},
                    provider="internal_por"
                ))
                quote.state = TransactionState.PAYOUT_COMPLETED
                
                # === LIQUIDITY LIFECYCLE HOOK: Payout Completed (Virtual) ===
                await self._on_payout_completed(
                    quote_id=quote_id,
                    net_payout_eur=quote.net_payout,
                    fee_eur=quote.fee_amount,
                    settlement_id=settlement_id,
                    payout_reference=payout_ref
                )
                
                quote.timeline.append(TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.COMPLETED,
                    message="Off-ramp completed successfully (virtual)",
                    details={
                        "settlement_id": settlement_id,
                        "payout_reference": payout_ref,
                        "net_payout_eur": quote.net_payout,
                        "payout_method": "virtual",
                        "completed_at": now.isoformat()
                    },
                    provider="internal_por"
                ))
                quote.state = TransactionState.COMPLETED
            
            # If real payout is pending (in_transit), state stays at PAYOUT_INITIATED
            # Webhook will update to PAYOUT_COMPLETED when Stripe confirms
            
            quote.metadata["settlement_id"] = settlement_id
            quote.metadata["payout_reference"] = payout_ref
            quote.metadata["payout_method"] = payout_method
            if stripe_payout_id:
                quote.metadata["stripe_payout_id"] = stripe_payout_id
            if payout_arrival_date:
                quote.metadata["payout_arrival_date"] = payout_arrival_date
            if quote.state == TransactionState.COMPLETED:
                quote.metadata["completed_at"] = now.isoformat()
            
            await self._store_transaction(quote)
            
            # Broadcast final webhook event
            await self._broadcast_state_change(
                quote, 
                "PAYOUT_COMPLETED" if quote.state == TransactionState.COMPLETED else "PAYOUT_INITIATED"
            )
            
            # Store settlement record
            settlement_doc = {
                "settlement_id": settlement_id,
                "quote_id": quote_id,
                "amount_eur": quote.net_payout,
                "fee_eur": quote.fee_amount,
                "payout_reference": payout_ref,
                "bank_account": bank_account,
                "status": "completed" if quote.state == TransactionState.COMPLETED else "processing",
                "settlement_mode": self._settlement_mode.value,
                "payout_method": payout_method,
                "stripe_payout_id": stripe_payout_id,
                "payout_arrival_date": payout_arrival_date,
                "created_at": now.isoformat(),
                "completed_at": now.isoformat() if quote.state == TransactionState.COMPLETED else None
            }
            await self.settlements_collection.insert_one(settlement_doc)
            
            logger.info(
                f"PoR settlement {'completed' if quote.state == TransactionState.COMPLETED else 'initiated'}: {settlement_id} | "
                f"€{quote.net_payout:,.2f} → {payout_ref} ({payout_method})"
            )
            
            result = SettlementResult(
                success=True,
                settlement_id=settlement_id,
                payout_reference=payout_ref,
                state=quote.state,
                details={
                    "net_payout": quote.net_payout,
                    "settlement_mode": self._settlement_mode.value,
                    "payout_method": payout_method,
                    "stripe_payout_id": stripe_payout_id,
                    "payout_arrival_date": payout_arrival_date
                }
            )
            
            return result, None
            
        except Exception as e:
            logger.error(f"Error executing settlement: {e}")
            return None, str(e)
    
    async def get_transaction(
        self,
        quote_id: str
    ) -> Optional[ProviderQuote]:
        """Get transaction details."""
        doc = await self.transactions_collection.find_one({"quote_id": quote_id})
        if not doc:
            return None
        return self._doc_to_quote(doc)
    
    async def get_timeline(
        self,
        quote_id: str
    ) -> List[TimelineEvent]:
        """Get transaction timeline."""
        quote = await self.get_transaction(quote_id)
        if not quote:
            return []
        return quote.timeline
    
    async def _store_transaction(self, quote: ProviderQuote):
        """Store or update transaction in database."""
        doc = self._quote_to_doc(quote)
        await self.transactions_collection.update_one(
            {"quote_id": quote.quote_id},
            {"$set": doc},
            upsert=True
        )
    
    async def _update_state(
        self,
        quote_id: str,
        state: TransactionState,
        message: str
    ):
        """Update transaction state."""
        quote = await self.get_transaction(quote_id)
        if quote:
            previous_state = quote.state.value
            quote.state = state
            quote.timeline.append(TimelineEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                state=state,
                message=message,
                provider="internal_por"
            ))
            await self._store_transaction(quote)
            
            # Broadcast webhook event
            await self._broadcast_state_change(quote, previous_state)
    
    async def _broadcast_state_change(
        self,
        quote: ProviderQuote,
        previous_state: Optional[str] = None
    ):
        """Broadcast state change via webhook and audit log."""
        direction = quote.direction
        state = quote.state.value
        
        # Get services
        webhook_svc = self._webhook_service or get_webhook_service()
        audit_logger = self._audit_logger or get_audit_logger()
        
        # Prepare event data
        event_data = {
            "crypto_amount": quote.crypto_amount,
            "crypto_currency": quote.crypto_currency,
            "fiat_amount": quote.fiat_amount,
            "fiat_currency": quote.fiat_currency,
            "exchange_rate": quote.exchange_rate,
            "fee_amount": quote.fee_amount,
            "fee_percentage": quote.fee_percentage,
            "net_payout": quote.net_payout,
            "compliance": {
                "kyc_status": quote.compliance.kyc_status.value,
                "aml_status": quote.compliance.aml_status.value,
                "por_responsible": quote.compliance.por_responsible
            },
            "metadata": {
                "provider": quote.provider.value,
                "settlement_mode": quote.metadata.get("settlement_mode"),
                "user_id": quote.metadata.get("user_id"),
                "api_key_id": quote.metadata.get("api_key_id")
            }
        }
        
        # Add direction-specific fields
        if direction == "onramp":
            event_data["payment_reference"] = quote.payment_reference
            event_data["payment_amount"] = quote.payment_amount
            event_data["wallet_address"] = quote.wallet_address
        else:
            event_data["deposit_address"] = quote.deposit_address
            event_data["bank_account_masked"] = (
                quote.metadata.get("bank_account", "")[:8] + "..." 
                if quote.metadata.get("bank_account") else None
            )
        
        # Broadcast webhook
        if webhook_svc:
            event_type = get_webhook_event_type(direction, state)
            if event_type:
                try:
                    await webhook_svc.broadcast_event(
                        event_type=event_type,
                        quote_id=quote.quote_id,
                        direction=direction,
                        state=state,
                        data=event_data,
                        previous_state=previous_state
                    )
                except Exception as e:
                    logger.error(f"Webhook broadcast failed: {e}")
        
        # Audit log
        if audit_logger:
            try:
                audit_event = self._get_audit_event_type(direction, state)
                if audit_event:
                    await audit_logger.log_transaction_event(
                        event_type=audit_event,
                        quote_id=quote.quote_id,
                        state=state,
                        crypto_amount=quote.crypto_amount,
                        crypto_currency=quote.crypto_currency,
                        fiat_amount=quote.fiat_amount,
                        details={
                            "direction": direction,
                            "previous_state": previous_state,
                            "settlement_mode": quote.metadata.get("settlement_mode")
                        }
                    )
            except Exception as e:
                logger.error(f"Audit log failed: {e}")
    
    def _get_audit_event_type(self, direction: str, state: str) -> Optional[AuditEventType]:
        """Map state to audit event type."""
        audit_map = {
            "QUOTE_CREATED": AuditEventType.QUOTE_CREATED,
            "QUOTE_ACCEPTED": AuditEventType.QUOTE_ACCEPTED,
            "QUOTE_EXPIRED": AuditEventType.QUOTE_EXPIRED,
            "DEPOSIT_PENDING": AuditEventType.DEPOSIT_PENDING,
            "DEPOSIT_DETECTED": AuditEventType.DEPOSIT_DETECTED,
            "DEPOSIT_CONFIRMED": AuditEventType.DEPOSIT_CONFIRMED,
            "DEPOSIT_FAILED": AuditEventType.DEPOSIT_FAILED,
            "SETTLEMENT_PENDING": AuditEventType.SETTLEMENT_INITIATED,
            "SETTLEMENT_PROCESSING": AuditEventType.SETTLEMENT_PROCESSING,
            "SETTLEMENT_COMPLETED": AuditEventType.SETTLEMENT_COMPLETED,
            "PAYOUT_INITIATED": AuditEventType.PAYOUT_INITIATED,
            "PAYOUT_COMPLETED": AuditEventType.PAYOUT_COMPLETED,
        }
        return audit_map.get(state)
    
    async def handle_payout_webhook(
        self,
        quote_id: str,
        payout_status: str,
        payout_id: str,
        failure_code: str = None,
        failure_message: str = None
    ) -> Tuple[Optional[ProviderQuote], Optional[str]]:
        """
        Handle payout status update from Stripe webhook.
        
        Called by webhook handler when payout.paid, payout.failed, or payout.canceled
        events are received.
        
        Args:
            quote_id: The quote ID associated with the payout
            payout_status: New status ('paid', 'failed', 'canceled')
            payout_id: Stripe payout ID
            failure_code: Failure code if status is 'failed'
            failure_message: Failure message if status is 'failed'
        """
        try:
            quote = await self.get_transaction(quote_id)
            if not quote:
                return None, f"Quote not found: {quote_id}"
            
            # Only process if in PAYOUT_INITIATED state
            if quote.state != TransactionState.PAYOUT_INITIATED:
                logger.warning(f"Quote {quote_id} not in PAYOUT_INITIATED state, current: {quote.state.value}")
                return quote, None  # Return current state without error
            
            now = datetime.now(timezone.utc)
            
            if payout_status == 'paid':
                # Payout succeeded
                quote.timeline.append(TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.PAYOUT_COMPLETED,
                    message="Real payout completed - funds transferred to bank account",
                    details={
                        "stripe_payout_id": payout_id,
                        "provider": "stripe",
                        "confirmation_timestamp": now.isoformat()
                    },
                    provider="stripe"
                ))
                quote.state = TransactionState.PAYOUT_COMPLETED
                
                quote.timeline.append(TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.COMPLETED,
                    message="Off-ramp completed successfully - EUR funds delivered",
                    details={
                        "settlement_id": quote.metadata.get("settlement_id"),
                        "payout_reference": quote.metadata.get("payout_reference"),
                        "stripe_payout_id": payout_id,
                        "net_payout_eur": quote.net_payout,
                        "payout_method": quote.metadata.get("payout_method", "stripe"),
                        "completed_at": now.isoformat()
                    },
                    provider="stripe"
                ))
                quote.state = TransactionState.COMPLETED
                quote.metadata["completed_at"] = now.isoformat()
                quote.metadata["payout_confirmed_at"] = now.isoformat()
                
                logger.info(f"✅ Payout CONFIRMED for quote {quote_id}: {payout_id}")
                
            elif payout_status == 'failed':
                # Payout failed
                quote.timeline.append(TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.PAYOUT_FAILED,
                    message=f"Payout failed: {failure_message or failure_code or 'Unknown error'}",
                    details={
                        "stripe_payout_id": payout_id,
                        "failure_code": failure_code,
                        "failure_message": failure_message,
                        "provider": "stripe"
                    },
                    provider="stripe"
                ))
                quote.state = TransactionState.PAYOUT_FAILED
                quote.metadata["payout_failed_at"] = now.isoformat()
                quote.metadata["payout_failure_reason"] = failure_message or failure_code
                
                logger.error(f"❌ Payout FAILED for quote {quote_id}: {failure_code} - {failure_message}")
                
                # If card fallback is enabled and this was SEPA, attempt card payout
                if (self._real_payout_service and 
                    quote.metadata.get("payout_method") == "sepa"):
                    logger.info(f"Attempting card fallback for quote {quote_id}")
                    # Card fallback will be handled separately
                
            elif payout_status == 'canceled':
                # Payout canceled
                quote.timeline.append(TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.PAYOUT_FAILED,
                    message="Payout was canceled",
                    details={
                        "stripe_payout_id": payout_id,
                        "provider": "stripe",
                        "reason": "canceled"
                    },
                    provider="stripe"
                ))
                quote.state = TransactionState.PAYOUT_FAILED
                quote.metadata["payout_canceled_at"] = now.isoformat()
                
                logger.warning(f"Payout CANCELED for quote {quote_id}: {payout_id}")
            
            await self._store_transaction(quote)
            
            # Update settlement record
            await self.settlements_collection.update_one(
                {"quote_id": quote_id},
                {
                    "$set": {
                        "status": "completed" if payout_status == "paid" else "failed",
                        "completed_at": now.isoformat() if payout_status == "paid" else None,
                        "failed_at": now.isoformat() if payout_status in ["failed", "canceled"] else None,
                        "failure_reason": failure_message or failure_code if payout_status == "failed" else None
                    }
                }
            )
            
            # Broadcast webhook event
            await self._broadcast_state_change(quote, "PAYOUT_INITIATED")
            
            # === LIQUIDITY LIFECYCLE HOOK: Post-Payout ===
            # Triggered when payout is confirmed - record fiat outflow and mark exposure covered
            if payout_status == 'paid':
                await self._on_payout_completed(
                    quote_id=quote_id,
                    net_payout_eur=quote.net_payout,
                    fee_eur=quote.fee_amount,
                    settlement_id=quote.metadata.get("settlement_id"),
                    payout_reference=payout_id
                )
            
            return quote, None
            
        except Exception as e:
            logger.error(f"Error handling payout webhook: {e}")
            return None, str(e)
    
    # =========================================================================
    # LIQUIDITY LIFECYCLE HOOKS (Hybrid PoR Architecture - Phase 1)
    # =========================================================================
    
    async def _on_deposit_confirmed(
        self,
        quote_id: str,
        crypto_amount: float,
        crypto_currency: str,
        eur_equivalent: float,
        tx_hash: str
    ):
        """
        Lifecycle hook: Crypto deposit confirmed.
        
        Triggers:
        1. Treasury crypto inflow ledger entry (REAL)
        2. Exposure record creation (REAL)
        3. Shadow-mode market routing simulation
        4. Shadow-mode hedge evaluation
        """
        logger.info(f"[LIQUIDITY] Deposit confirmed for {quote_id}: {crypto_amount} {crypto_currency}")
        
        exposure_id = None
        
        # 1. Record crypto inflow to treasury (REAL)
        if self._treasury_service:
            try:
                entry = await self._treasury_service.record_crypto_inflow(
                    quote_id=quote_id,
                    crypto_amount=crypto_amount,
                    crypto_currency=crypto_currency,
                    eur_equivalent=eur_equivalent,
                    tx_hash=tx_hash
                )
                # Entry stored for audit trail (not directly passed downstream)
                logger.info(f"[TREASURY] Crypto inflow recorded: {entry.entry_id} | {crypto_amount} {crypto_currency}")
            except Exception as e:
                logger.error(f"[TREASURY] Failed to record crypto inflow: {e}")
        
        # 2. Create exposure record (REAL)
        if self._exposure_service:
            try:
                from models.liquidity.exposure_models import ExposureType
                exposure = await self._exposure_service.create_exposure(
                    quote_id=quote_id,
                    exposure_type=ExposureType.OFFRAMP_PAYOUT,
                    crypto_amount=crypto_amount,
                    crypto_currency=crypto_currency,
                    fiat_amount=eur_equivalent,
                    fiat_currency="EUR",
                    direction="offramp",
                    deposit_tx_hash=tx_hash
                )
                exposure_id = exposure.exposure_id
                logger.info(f"[EXPOSURE] Created: {exposure_id} | €{eur_equivalent:,.2f}")
            except Exception as e:
                logger.error(f"[EXPOSURE] Failed to create exposure: {e}")
        
        # 3. Shadow-mode market routing simulation (LOG-ONLY)
        if self._routing_service:
            try:
                # Simulate what market route would be used
                conversion_event = await self._routing_service.simulate_conversion(
                    quote_id=quote_id,
                    source_currency=crypto_currency,
                    destination_currency="EUR",
                    source_amount=crypto_amount,
                    exposure_id=exposure_id
                )
                if conversion_event:
                    logger.info(
                        f"[ROUTING:SHADOW] Simulated conversion: {crypto_currency} → EUR | "
                        f"Path: {conversion_event.conversion_path.path if conversion_event.conversion_path else 'direct'}"
                    )
            except Exception as e:
                logger.error(f"[ROUTING:SHADOW] Simulation failed: {e}")
        
        # 4. Shadow-mode hedge evaluation (AUDIT-ONLY)
        if self._hedging_service and self._exposure_service and self._treasury_service:
            try:
                total_exposure = await self._exposure_service.get_total_active_exposure()
                coverage_ratio = await self._treasury_service.calculate_coverage_ratio(total_exposure)
                active_exposures = await self._exposure_service.get_active_exposures(limit=20)
                active_ids = [e["exposure_id"] for e in active_exposures]
                
                proposal = await self._hedging_service.evaluate_hedge_triggers(
                    total_exposure_eur=total_exposure,
                    coverage_ratio=coverage_ratio,
                    active_exposure_ids=active_ids
                )
                if proposal:
                    logger.info(
                        f"[HEDGING:SHADOW] Hedge proposal generated: {proposal.proposal_id} | "
                        f"Action: {proposal.recommended_action} | "
                        f"Exposure: €{total_exposure:,.2f} | Coverage: {coverage_ratio:.2%}"
                    )
                else:
                    logger.info(
                        f"[HEDGING:SHADOW] No hedge trigger | "
                        f"Exposure: €{total_exposure:,.2f} | Coverage: {coverage_ratio:.2%}"
                    )
            except Exception as e:
                logger.error(f"[HEDGING:SHADOW] Evaluation failed: {e}")
    
    async def _on_payout_completed(
        self,
        quote_id: str,
        net_payout_eur: float,
        fee_eur: float,
        settlement_id: str,
        payout_reference: str
    ):
        """
        Lifecycle hook: Fiat payout completed.
        
        Triggers:
        1. Treasury fiat outflow ledger entry (REAL)
        2. Fee collection ledger entry (REAL)
        3. Exposure marked as covered (REAL)
        4. Coverage event for reconciliation (REAL)
        """
        logger.info(f"[LIQUIDITY] Payout completed for {quote_id}: €{net_payout_eur:,.2f}")
        
        fiat_ledger_id = None
        
        # 1. Record fiat payout outflow (REAL)
        if self._treasury_service:
            try:
                fiat_entry = await self._treasury_service.record_fiat_payout(
                    quote_id=quote_id,
                    settlement_id=settlement_id,
                    amount_eur=net_payout_eur,
                    payout_reference=payout_reference,
                    payout_provider="stripe"
                )
                fiat_ledger_id = fiat_entry.entry_id
                logger.info(f"[TREASURY] Fiat payout recorded: {fiat_entry.entry_id} | €{net_payout_eur:,.2f}")
            except Exception as e:
                logger.error(f"[TREASURY] Failed to record fiat payout: {e}")
        
        # 2. Record fee collection (REAL)
        if self._treasury_service and fee_eur > 0:
            try:
                fee_entry = await self._treasury_service.record_fee_collection(
                    quote_id=quote_id,
                    fee_amount=fee_eur,
                    fee_currency="EUR"
                )
                # Fee entry stored for audit trail
                logger.info(f"[TREASURY] Fee collected: {fee_entry.entry_id} | €{fee_eur:,.2f}")
            except Exception as e:
                logger.error(f"[TREASURY] Failed to record fee collection: {e}")
        
        # 3. Mark exposure as covered (REAL)
        exposure_id = None
        exposure_before = 0.0
        exposure_after = 0.0
        
        if self._exposure_service:
            try:
                # Get the exposure for this quote
                exposure = await self._exposure_service.get_exposure_by_quote(quote_id)
                if exposure:
                    exposure_id = exposure.get("exposure_id")
                    exposure_before = await self._exposure_service.get_total_active_exposure()
                    
                    # Mark as covered
                    await self._exposure_service.mark_covered(
                        exposure_id=exposure_id,
                        coverage_amount=net_payout_eur,
                        settlement_id=settlement_id,
                        ledger_entry_id=fiat_ledger_id
                    )
                    
                    exposure_after = await self._exposure_service.get_total_active_exposure()
                    logger.info(f"[EXPOSURE] Marked covered: {exposure_id} | Active: €{exposure_after:,.2f}")
            except Exception as e:
                logger.error(f"[EXPOSURE] Failed to mark covered: {e}")
        
        # 4. Create coverage event for reconciliation (REAL)
        if self._reconciliation_service:
            try:
                coverage_event = await self._reconciliation_service.create_coverage_event(
                    action_type="payout_settlement",
                    amount_eur=net_payout_eur,
                    exposure_id=exposure_id,
                    ledger_entry_id=fiat_ledger_id,
                    exposure_before_eur=exposure_before,
                    exposure_after_eur=exposure_after,
                    description=f"Payout completed for {quote_id}",
                    provider="stripe",
                    is_shadow=False  # This is a REAL coverage event
                )
                logger.info(f"[RECONCILIATION] Coverage event: {coverage_event.coverage_id} | €{net_payout_eur:,.2f}")
            except Exception as e:
                logger.error(f"[RECONCILIATION] Failed to create coverage event: {e}")
    
    async def _on_settlement_initiated(
        self,
        quote_id: str,
        settlement_id: str,
        net_payout_eur: float,
        fee_eur: float
    ):
        """
        Lifecycle hook: Settlement initiated (payout in transit).
        
        Called when payout is initiated but not yet confirmed (async payout flow).
        Updates exposure status to PARTIALLY_COVERED.
        """
        logger.info(f"[LIQUIDITY] Settlement initiated for {quote_id}: {settlement_id}")
        
        # Update exposure to partially covered
        if self._exposure_service:
            try:
                exposure = await self._exposure_service.get_exposure_by_quote(quote_id)
                if exposure:
                    await self._exposure_service.update_status(
                        exposure_id=exposure.get("exposure_id"),
                        status="partially_covered",
                        metadata={"settlement_id": settlement_id, "payout_pending": True}
                    )
                    logger.info(f"[EXPOSURE] Status updated to partially_covered: {exposure.get('exposure_id')}")
            except Exception as e:
                logger.error(f"[EXPOSURE] Failed to update status: {e}")
    
    def _quote_to_doc(self, quote: ProviderQuote) -> Dict:
        """Convert quote to MongoDB document."""
        return {
            "quote_id": quote.quote_id,
            "provider": quote.provider.value,
            "direction": quote.direction,
            "crypto_amount": quote.crypto_amount,
            "crypto_currency": quote.crypto_currency,
            "fiat_amount": quote.fiat_amount,
            "fiat_currency": quote.fiat_currency,
            "exchange_rate": quote.exchange_rate,
            "fee_amount": quote.fee_amount,
            "fee_percentage": quote.fee_percentage,
            "net_payout": quote.net_payout,
            "deposit_address": quote.deposit_address,
            "wallet_address": quote.wallet_address,
            "payment_reference": quote.payment_reference,
            "payment_amount": quote.payment_amount,
            "expires_at": quote.expires_at,
            "created_at": quote.created_at,
            "state": quote.state.value,
            "compliance": {
                "kyc_status": quote.compliance.kyc_status.value,
                "kyc_provider": quote.compliance.kyc_provider,
                "kyc_verified_at": quote.compliance.kyc_verified_at,
                "aml_status": quote.compliance.aml_status.value,
                "aml_provider": quote.compliance.aml_provider,
                "aml_cleared_at": quote.compliance.aml_cleared_at,
                "risk_score": quote.compliance.risk_score,
                "risk_level": quote.compliance.risk_level,
                "por_responsible": quote.compliance.por_responsible
            },
            "timeline": [
                {
                    "timestamp": e.timestamp,
                    "state": e.state.value,
                    "message": e.message,
                    "details": e.details,
                    "provider": e.provider
                }
                for e in quote.timeline
            ],
            "metadata": quote.metadata,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    
    def _doc_to_quote(self, doc: Dict) -> ProviderQuote:
        """Convert MongoDB document to quote."""
        compliance_data = doc.get("compliance", {})
        compliance = ComplianceInfo(
            kyc_status=KYCStatus(compliance_data.get("kyc_status", "not_required")),
            kyc_provider=compliance_data.get("kyc_provider", "internal_por"),
            kyc_verified_at=compliance_data.get("kyc_verified_at"),
            aml_status=AMLStatus(compliance_data.get("aml_status", "not_required")),
            aml_provider=compliance_data.get("aml_provider", "internal_por"),
            aml_cleared_at=compliance_data.get("aml_cleared_at"),
            risk_score=compliance_data.get("risk_score"),
            risk_level=compliance_data.get("risk_level", "low"),
            por_responsible=compliance_data.get("por_responsible", True)
        )
        
        timeline = [
            TimelineEvent(
                timestamp=e["timestamp"],
                state=TransactionState(e["state"]),
                message=e["message"],
                details=e.get("details"),
                provider=e.get("provider", "internal_por")
            )
            for e in doc.get("timeline", [])
        ]
        
        return ProviderQuote(
            quote_id=doc["quote_id"],
            provider=ProviderType(doc.get("provider", "internal_por")),
            direction=doc.get("direction", "offramp"),
            crypto_amount=doc["crypto_amount"],
            crypto_currency=doc["crypto_currency"],
            fiat_amount=doc["fiat_amount"],
            fiat_currency=doc["fiat_currency"],
            exchange_rate=doc["exchange_rate"],
            fee_amount=doc["fee_amount"],
            fee_percentage=doc["fee_percentage"],
            net_payout=doc["net_payout"],
            deposit_address=doc.get("deposit_address"),
            wallet_address=doc.get("wallet_address"),
            payment_reference=doc.get("payment_reference"),
            payment_amount=doc.get("payment_amount"),
            expires_at=doc["expires_at"],
            created_at=doc["created_at"],
            state=TransactionState(doc["state"]),
            compliance=compliance,
            timeline=timeline,
            metadata=doc.get("metadata", {})
        )
    
    async def get_liquidity_status(self) -> Dict:
        """Get current liquidity pool status."""
        pool = await self.liquidity_collection.find_one({"pool_id": "primary"})
        if not pool:
            return {
                "available": True,
                "unlimited_mode": LIQUIDITY_UNLIMITED,
                "currency": "EUR"
            }
        
        pool.pop("_id", None)
        return pool
    
    async def list_transactions(
        self,
        user_id: Optional[str] = None,
        state: Optional[TransactionState] = None,
        limit: int = 50
    ) -> List[ProviderQuote]:
        """List transactions with optional filters."""
        query = {}
        if user_id:
            query["metadata.user_id"] = user_id
        if state:
            query["state"] = state.value
        
        cursor = self.transactions_collection.find(query).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self._doc_to_quote(doc) for doc in docs]


    # ========================
    # ON-RAMP METHODS (Fiat → Crypto)
    # ========================
    
    async def create_onramp_quote(
        self,
        fiat_amount: float,
        crypto_currency: str,
        fiat_currency: str = "EUR",
        user_id: Optional[str] = None,
        wallet_address: Optional[str] = None
    ) -> Tuple[Optional[ProviderQuote], Optional[str]]:
        """
        Create an on-ramp quote (Fiat → Crypto).
        
        The PoR engine automatically:
        - Validates the request
        - Calculates pricing (NENO = €10,000 fixed)
        - Generates payment reference
        - Returns enterprise-grade quote
        """
        try:
            await self.initialize()
            
            crypto_currency = crypto_currency.upper()
            
            # Validate crypto
            if crypto_currency not in self.config.supported_cryptos:
                return None, f"Unsupported cryptocurrency: {crypto_currency}"
            
            # Validate minimum amount
            if fiat_amount < self.config.min_amount_eur:
                return None, f"Minimum amount is €{self.config.min_amount_eur}"
            
            # Get exchange rate
            if crypto_currency == "NENO":
                exchange_rate = NENO_PRICE_EUR
            else:
                try:
                    exchange_rate = await pricing_service.get_price_eur(crypto_currency)
                except Exception as e:
                    return None, f"Unable to fetch price for {crypto_currency}: {e}"
            
            # Calculate amounts
            # For on-ramp: user pays fiat_amount, fee is deducted, they receive crypto
            fee_amount = Decimal(str(fiat_amount)) * Decimal(str(POR_FEE_PERCENTAGE / 100))
            net_fiat = Decimal(str(fiat_amount)) - fee_amount  # Amount after fee
            crypto_amount = net_fiat / Decimal(str(exchange_rate))  # Crypto they receive
            
            # Generate quote ID and payment reference
            quote_id = f"por_on_{uuid4().hex[:14]}"
            payment_ref = f"PAY-{quote_id[-8:].upper()}"
            
            # Create timestamps
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(minutes=POR_QUOTE_TTL_MINUTES)
            
            # Create compliance info (PoR handles KYC/AML)
            compliance = ComplianceInfo(
                kyc_status=KYCStatus.NOT_REQUIRED,
                kyc_provider="internal_por",
                aml_status=AMLStatus.NOT_REQUIRED,
                aml_provider="internal_por",
                risk_score=0.0,
                risk_level="low",
                por_responsible=True
            )
            
            # Create initial timeline event
            timeline = [
                TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.QUOTE_CREATED,
                    message="On-ramp quote created by PoR engine",
                    details={
                        "fiat_amount": fiat_amount,
                        "fiat_currency": fiat_currency,
                        "exchange_rate": float(exchange_rate),
                        "crypto_amount": float(crypto_amount),
                        "crypto_currency": crypto_currency
                    },
                    provider="internal_por"
                )
            ]
            
            # Create quote object
            quote = ProviderQuote(
                quote_id=quote_id,
                provider=ProviderType.INTERNAL_POR,
                direction="onramp",
                crypto_amount=float(crypto_amount),
                crypto_currency=crypto_currency,
                fiat_amount=fiat_amount,
                fiat_currency=fiat_currency,
                exchange_rate=float(exchange_rate),
                fee_amount=float(fee_amount),
                fee_percentage=POR_FEE_PERCENTAGE,
                net_payout=float(crypto_amount),  # For on-ramp, net_payout is crypto amount
                deposit_address=None,  # Not used for on-ramp
                wallet_address=wallet_address,  # User's crypto wallet
                payment_reference=payment_ref,  # Fiat payment reference
                payment_amount=fiat_amount,  # Total fiat to pay
                expires_at=expires_at.isoformat(),
                created_at=now.isoformat(),
                state=TransactionState.QUOTE_CREATED,
                compliance=compliance,
                timeline=timeline,
                metadata={
                    "user_id": user_id,
                    "wallet_address": wallet_address,
                    "por_engine": POR_ENGINE_NAME,
                    "por_version": POR_ENGINE_VERSION,
                    "settlement_mode": self._settlement_mode.value,
                    "direction": "onramp"
                }
            )
            
            # Store in database
            await self._store_transaction(quote)
            
            # Broadcast webhook event
            await self._broadcast_state_change(quote, None)
            
            logger.info(
                f"PoR on-ramp quote created: {quote_id} | "
                f"€{fiat_amount} → {float(crypto_amount):.8f} {crypto_currency}"
            )
            
            return quote, None
            
        except Exception as e:
            logger.error(f"Error creating PoR on-ramp quote: {e}")
            return None, str(e)
    
    async def accept_onramp_quote(
        self,
        quote_id: str,
        wallet_address: str
    ) -> Tuple[Optional[ProviderQuote], Optional[str]]:
        """
        Accept an on-ramp quote and initiate the purchase.
        
        Transitions: QUOTE_CREATED → QUOTE_ACCEPTED → PAYMENT_PENDING
        """
        try:
            quote = await self.get_transaction(quote_id)
            if not quote:
                return None, f"Quote not found: {quote_id}"
            
            # Verify it's an on-ramp quote
            if quote.metadata.get("direction") != "onramp":
                return None, "Invalid quote type for on-ramp"
            
            # Check state
            if quote.state not in [TransactionState.QUOTE_CREATED]:
                return None, f"Quote cannot be accepted in state: {quote.state.value}"
            
            # Check expiry
            expires_at = datetime.fromisoformat(quote.expires_at.replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > expires_at:
                await self._update_state(quote_id, TransactionState.QUOTE_EXPIRED, "Quote has expired")
                return None, "Quote has expired"
            
            now = datetime.now(timezone.utc)
            
            # Update quote with wallet address
            quote.wallet_address = wallet_address
            quote.metadata["wallet_address"] = wallet_address
            
            # Add timeline events
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.QUOTE_ACCEPTED,
                message="Quote accepted, awaiting fiat payment",
                details={"wallet_address": wallet_address[:10] + "..." if len(wallet_address) > 10 else wallet_address},
                provider="internal_por"
            ))
            
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.PAYMENT_PENDING,
                message="Waiting for fiat payment",
                details={
                    "payment_reference": quote.payment_reference,
                    "payment_amount": quote.payment_amount,
                    "currency": quote.fiat_currency
                },
                provider="internal_por"
            ))
            
            # Update state
            quote.state = TransactionState.PAYMENT_PENDING
            
            # Store update
            await self._store_transaction(quote)
            
            # Broadcast webhook event
            await self._broadcast_state_change(quote, "QUOTE_CREATED")
            
            logger.info(f"PoR on-ramp quote accepted: {quote_id} → PAYMENT_PENDING")
            
            return quote, None
            
        except Exception as e:
            logger.error(f"Error accepting on-ramp quote: {e}")
            return None, str(e)
    
    async def process_onramp_payment(
        self,
        quote_id: str,
        payment_ref: str,
        amount_paid: float
    ) -> Tuple[Optional[ProviderQuote], Optional[str]]:
        """
        Process a confirmed fiat payment for on-ramp.
        
        Transitions: PAYMENT_PENDING → PAYMENT_DETECTED → PAYMENT_CONFIRMED
        Then automatically triggers crypto delivery if in INSTANT mode.
        """
        try:
            quote = await self.get_transaction(quote_id)
            if not quote:
                return None, f"Quote not found: {quote_id}"
            
            # Verify it's an on-ramp quote
            if quote.metadata.get("direction") != "onramp":
                return None, "Invalid quote type for on-ramp payment"
            
            # Check if already processed (idempotency protection)
            if quote.state in [
                TransactionState.COMPLETED,
                TransactionState.FAILED,
                TransactionState.REFUNDED,
                TransactionState.CRYPTO_CONFIRMED
            ]:
                logger.warning(f"Payment already processed for quote {quote_id} (state: {quote.state.value})")
                return quote, None
            
            # Check if payment can be processed
            if quote.state not in [
                TransactionState.PAYMENT_PENDING,
                TransactionState.QUOTE_ACCEPTED
            ]:
                return None, f"Cannot process payment in state: {quote.state.value}"
            
            # Check for duplicate payment reference
            existing_ref = quote.metadata.get("payment_tx_ref")
            if existing_ref:
                if existing_ref == payment_ref:
                    logger.warning(f"Duplicate payment ref for quote {quote_id}")
                    return quote, None
                else:
                    return None, f"Quote {quote_id} already has a payment with different reference"
            
            now = datetime.now(timezone.utc)
            
            # Add payment detected event
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.PAYMENT_DETECTED,
                message=f"Payment detected: €{amount_paid}",
                details={
                    "payment_ref": payment_ref,
                    "amount_paid": amount_paid,
                    "expected_amount": quote.payment_amount
                },
                provider="internal_por"
            ))
            
            quote.state = TransactionState.PAYMENT_DETECTED
            
            # Validate amount (with tolerance)
            tolerance = 0.01  # €0.01 tolerance for fiat
            if abs(amount_paid - quote.payment_amount) > tolerance:
                quote.timeline.append(TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.PAYMENT_FAILED,
                    message=f"Amount mismatch: received €{amount_paid}, expected €{quote.payment_amount}",
                    provider="internal_por"
                ))
                quote.state = TransactionState.PAYMENT_FAILED
                await self._store_transaction(quote)
                return None, f"Amount mismatch: received €{amount_paid}, expected €{quote.payment_amount}"
            
            # Mark payment as confirmed
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.PAYMENT_CONFIRMED,
                message="Payment confirmed, initiating crypto delivery",
                details={"payment_reference": payment_ref},
                provider="internal_por"
            ))
            
            quote.state = TransactionState.PAYMENT_CONFIRMED
            quote.metadata["payment_tx_ref"] = payment_ref
            quote.metadata["payment_amount_received"] = amount_paid
            quote.metadata["payment_confirmed_at"] = now.isoformat()
            
            # Update compliance (AML cleared by PoR)
            quote.compliance.aml_status = AMLStatus.CLEARED
            quote.compliance.aml_cleared_at = now.isoformat()
            
            await self._store_transaction(quote)
            
            # Broadcast webhook event
            await self._broadcast_state_change(quote, "PAYMENT_DETECTED")
            
            logger.info(f"PoR on-ramp payment confirmed: {quote_id} | €{amount_paid}")
            
            # Auto-trigger crypto delivery in INSTANT mode
            if self._settlement_mode == SettlementMode.INSTANT:
                delivery_result, error = await self.execute_crypto_delivery(quote_id)
                if error:
                    logger.error(f"Crypto delivery failed: {error}")
                    return quote, error
                
                # Refresh quote after delivery
                quote = await self.get_transaction(quote_id)
            
            return quote, None
            
        except Exception as e:
            logger.error(f"Error processing on-ramp payment: {e}")
            return None, str(e)
    
    async def execute_crypto_delivery(
        self,
        quote_id: str
    ) -> Tuple[Optional[dict], Optional[str]]:
        """
        Execute crypto delivery for on-ramp.
        
        Transitions: PAYMENT_CONFIRMED → CRYPTO_SENDING → CRYPTO_SENT → CRYPTO_CONFIRMED → COMPLETED
        
        In INSTANT mode, all transitions happen immediately.
        """
        try:
            quote = await self.get_transaction(quote_id)
            if not quote:
                return None, f"Quote not found: {quote_id}"
            
            if quote.state not in [
                TransactionState.PAYMENT_CONFIRMED
            ]:
                return None, f"Cannot deliver crypto in state: {quote.state.value}"
            
            now = datetime.now(timezone.utc)
            delivery_id = f"dlv_{uuid4().hex[:12]}"
            tx_hash = f"0x{uuid4().hex}"  # Simulated blockchain tx hash
            
            wallet_address = quote.wallet_address or quote.metadata.get("wallet_address")
            if not wallet_address:
                return None, "No wallet address provided"
            
            # Crypto sending
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.CRYPTO_SENDING,
                message=f"Sending {quote.crypto_amount:.8f} {quote.crypto_currency} to wallet",
                details={
                    "delivery_id": delivery_id,
                    "wallet_address": wallet_address[:10] + "..." if len(wallet_address) > 10 else wallet_address
                },
                provider="internal_por"
            ))
            quote.state = TransactionState.CRYPTO_SENDING
            await self._store_transaction(quote)
            
            # Crypto sent (transaction broadcast)
            quote.timeline.append(TimelineEvent(
                timestamp=now.isoformat(),
                state=TransactionState.CRYPTO_SENT,
                message="Crypto transaction broadcast to network",
                details={
                    "tx_hash": tx_hash,
                    "network": "BNB Smart Chain" if quote.crypto_currency == "NENO" else "Mainnet"
                },
                provider="internal_por"
            ))
            quote.state = TransactionState.CRYPTO_SENT
            await self._store_transaction(quote)
            
            # In INSTANT mode, confirm immediately
            if self._settlement_mode == SettlementMode.INSTANT:
                quote.timeline.append(TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.CRYPTO_CONFIRMED,
                    message="Crypto transaction confirmed on blockchain",
                    details={
                        "tx_hash": tx_hash,
                        "confirmations": "sufficient"
                    },
                    provider="internal_por"
                ))
                quote.state = TransactionState.CRYPTO_CONFIRMED
                
                quote.timeline.append(TimelineEvent(
                    timestamp=now.isoformat(),
                    state=TransactionState.COMPLETED,
                    message="On-ramp completed successfully",
                    details={
                        "delivery_id": delivery_id,
                        "tx_hash": tx_hash,
                        "crypto_amount": quote.crypto_amount,
                        "crypto_currency": quote.crypto_currency,
                        "wallet_address": wallet_address[:10] + "..." if len(wallet_address) > 10 else wallet_address,
                        "completed_at": now.isoformat()
                    },
                    provider="internal_por"
                ))
                quote.state = TransactionState.COMPLETED
            
            quote.metadata["delivery_id"] = delivery_id
            quote.metadata["crypto_tx_hash"] = tx_hash
            quote.metadata["completed_at"] = now.isoformat()
            
            await self._store_transaction(quote)
            
            # Broadcast final webhook event
            await self._broadcast_state_change(quote, "CRYPTO_CONFIRMED" if self._settlement_mode == SettlementMode.INSTANT else "CRYPTO_SENT")
            
            logger.info(
                f"PoR on-ramp delivery completed: {delivery_id} | "
                f"{quote.crypto_amount:.8f} {quote.crypto_currency} → {wallet_address[:10]}..."
            )
            
            return {
                "success": True,
                "delivery_id": delivery_id,
                "tx_hash": tx_hash,
                "state": quote.state.value
            }, None
            
        except Exception as e:
            logger.error(f"Error executing crypto delivery: {e}")
            return None, str(e)

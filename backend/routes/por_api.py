"""
PoR Engine API Routes.

Enterprise-grade off-ramp API endpoints powered by the
internal Provider-of-Record engine.

Available to both:
- End-users via UI authentication (JWT)
- Developers via API Keys (HMAC)
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
import logging

from services.por_engine import InternalPoRProvider
from services.provider_interface import (
    TransactionState,
    SettlementMode,
    ProviderQuote
)
from middleware.auth import get_current_user, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/por", tags=["Provider-of-Record Engine"])

# PoR engine will be set by main app
por_engine: InternalPoRProvider = None


def set_por_engine(engine: InternalPoRProvider):
    global por_engine
    por_engine = engine


# ========================
# Request/Response Models
# ========================

class CreateQuoteRequest(BaseModel):
    crypto_amount: float = Field(..., gt=0, description="Amount of crypto to sell")
    crypto_currency: str = Field(default="NENO", description="Cryptocurrency (NENO, BTC, ETH, etc.)")
    fiat_currency: str = Field(default="EUR", description="Fiat currency for payout")
    bank_account: Optional[str] = Field(None, description="IBAN for payout")


class AcceptQuoteRequest(BaseModel):
    quote_id: str = Field(..., description="Quote ID to accept")
    bank_account: str = Field(..., description="IBAN for payout")


class ProcessDepositRequest(BaseModel):
    quote_id: str = Field(..., description="Quote ID")
    tx_hash: str = Field(..., description="Blockchain transaction hash")
    amount: float = Field(..., description="Amount received")


class SettlementModeRequest(BaseModel):
    mode: str = Field(..., description="Settlement mode: instant, simulated_delay, or batch")


class QuoteResponse(BaseModel):
    quote_id: str
    provider: str
    crypto_amount: float
    crypto_currency: str
    fiat_amount: float
    fiat_currency: str
    exchange_rate: float
    fee_amount: float
    fee_percentage: float
    net_payout: float
    deposit_address: Optional[str]
    expires_at: str
    created_at: str
    state: str
    compliance: dict
    timeline: list
    metadata: dict

    class Config:
        from_attributes = True


class TimelineEventResponse(BaseModel):
    timestamp: str
    state: str
    message: str
    details: Optional[dict]
    provider: str


class TransactionListResponse(BaseModel):
    count: int
    transactions: List[QuoteResponse]


# ========================
# Utility Functions
# ========================

def quote_to_response(quote: ProviderQuote) -> dict:
    """Convert ProviderQuote to API response dict."""
    return {
        "quote_id": quote.quote_id,
        "provider": quote.provider.value,
        "crypto_amount": quote.crypto_amount,
        "crypto_currency": quote.crypto_currency,
        "fiat_amount": quote.fiat_amount,
        "fiat_currency": quote.fiat_currency,
        "exchange_rate": quote.exchange_rate,
        "fee_amount": quote.fee_amount,
        "fee_percentage": quote.fee_percentage,
        "net_payout": quote.net_payout,
        "deposit_address": quote.deposit_address,
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
        "metadata": quote.metadata
    }


# ========================
# API Endpoints
# ========================

@router.get("/status")
async def get_por_status():
    """
    Get PoR engine status.
    
    Returns provider configuration, liquidity status, and capabilities.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not initialized")
    
    config = por_engine.get_config()
    liquidity = await por_engine.get_liquidity_status()
    
    return {
        "provider": {
            "type": config.provider_type.value,
            "name": config.name,
            "enabled": config.enabled,
            "version": "2.0.0"
        },
        "capabilities": {
            "settlement_mode": config.settlement_mode.value,
            "fee_percentage": config.fee_percentage,
            "min_amount_eur": config.min_amount_eur,
            "max_amount_eur": config.max_amount_eur,
            "supported_currencies": config.supported_currencies,
            "supported_cryptos": config.supported_cryptos,
            "kyc_required": config.kyc_required,
            "aml_required": config.aml_required
        },
        "liquidity": liquidity,
        "available": por_engine.is_available()
    }


@router.post("/quote")
async def create_quote(
    request: CreateQuoteRequest,
    user: dict = Depends(get_optional_user)
):
    """
    Create an off-ramp quote.
    
    The PoR engine automatically:
    - Validates the request
    - Calculates pricing (NENO = €10,000 fixed)
    - Generates deposit address
    - Returns enterprise-grade quote with full lifecycle
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not initialized")
    
    user_id = user.get("id") if user else None
    
    quote, error = await por_engine.create_quote(
        crypto_amount=request.crypto_amount,
        crypto_currency=request.crypto_currency,
        fiat_currency=request.fiat_currency,
        user_id=user_id,
        bank_account=request.bank_account
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    return quote_to_response(quote)


@router.post("/quote/accept")
async def accept_quote(
    request: AcceptQuoteRequest,
    user: dict = Depends(get_optional_user)
):
    """
    Accept a quote and initiate the off-ramp.
    
    Transitions the quote to DEPOSIT_PENDING state.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not initialized")
    
    quote, error = await por_engine.accept_quote(
        quote_id=request.quote_id,
        bank_account=request.bank_account
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    return quote_to_response(quote)


@router.post("/deposit/process")
async def process_deposit(request: ProcessDepositRequest):
    """
    Process a detected crypto deposit.
    
    Called when blockchain listener detects deposit.
    In INSTANT settlement mode, automatically completes the transaction.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not initialized")
    
    quote, error = await por_engine.process_deposit(
        quote_id=request.quote_id,
        tx_hash=request.tx_hash,
        amount=request.amount
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    return quote_to_response(quote)


@router.post("/settlement/execute/{quote_id}")
async def execute_settlement(quote_id: str):
    """
    Manually execute settlement for a quote.
    
    Used when settlement_mode is not INSTANT.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not initialized")
    
    result, error = await por_engine.execute_settlement(quote_id)
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    return {
        "success": result.success,
        "settlement_id": result.settlement_id,
        "payout_reference": result.payout_reference,
        "state": result.state.value,
        "details": result.details
    }


@router.get("/transaction/{quote_id}")
async def get_transaction(quote_id: str):
    """
    Get transaction details by quote ID.
    
    Returns full transaction data including:
    - Quote details
    - Current state
    - Compliance info (KYC/AML)
    - Timeline events
    - Metadata
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not initialized")
    
    quote = await por_engine.get_transaction(quote_id)
    
    if not quote:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    return quote_to_response(quote)


@router.get("/transaction/{quote_id}/timeline")
async def get_transaction_timeline(quote_id: str):
    """
    Get transaction timeline (event history).
    
    Returns detailed event log with:
    - Timestamps
    - State transitions
    - Messages
    - Provider info
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not initialized")
    
    timeline = await por_engine.get_timeline(quote_id)
    
    if not timeline:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    return {
        "quote_id": quote_id,
        "event_count": len(timeline),
        "events": [
            {
                "timestamp": e.timestamp,
                "state": e.state.value,
                "message": e.message,
                "details": e.details,
                "provider": e.provider
            }
            for e in timeline
        ]
    }


@router.get("/transactions")
async def list_transactions(
    state: Optional[str] = Query(None, description="Filter by state"),
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(get_optional_user)
):
    """
    List transactions with optional filters.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not initialized")
    
    user_id = user.get("id") if user else None
    state_filter = TransactionState(state) if state else None
    
    transactions = await por_engine.list_transactions(
        user_id=user_id,
        state=state_filter,
        limit=limit
    )
    
    return {
        "count": len(transactions),
        "transactions": [quote_to_response(q) for q in transactions]
    }


@router.get("/liquidity")
async def get_liquidity_status():
    """
    Get PoR liquidity pool status.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not initialized")
    
    return await por_engine.get_liquidity_status()


@router.post("/config/settlement-mode")
async def set_settlement_mode(request: SettlementModeRequest):
    """
    Configure settlement mode.
    
    Available modes:
    - instant: Immediate settlement (default)
    - simulated_delay: Realistic banking delay
    - batch: Scheduled batch processing
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not initialized")
    
    try:
        mode = SettlementMode(request.mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid settlement mode. Valid: instant, simulated_delay, batch"
        )
    
    por_engine.set_settlement_mode(mode)
    
    return {
        "settlement_mode": mode.value,
        "message": f"Settlement mode changed to {mode.value}"
    }


# ========================
# Developer API Endpoints
# ========================

@router.get("/developer/supported-cryptos")
async def get_supported_cryptos():
    """
    Get list of supported cryptocurrencies.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not initialized")
    
    config = por_engine.get_config()
    
    return {
        "supported_cryptos": config.supported_cryptos,
        "supported_currencies": config.supported_currencies,
        "neno_price_eur": 10000.0,
        "fee_percentage": config.fee_percentage
    }


@router.get("/developer/transaction-states")
async def get_transaction_states():
    """
    Get all possible transaction states.
    
    Useful for developers to understand the lifecycle.
    """
    return {
        "states": [
            {
                "value": state.value,
                "description": _get_state_description(state)
            }
            for state in TransactionState
        ]
    }


def _get_state_description(state: TransactionState) -> str:
    """Get human-readable description for a state."""
    descriptions = {
        TransactionState.QUOTE_CREATED: "Quote created, awaiting acceptance",
        TransactionState.QUOTE_ACCEPTED: "Quote accepted, awaiting deposit",
        TransactionState.QUOTE_EXPIRED: "Quote expired before acceptance",
        TransactionState.QUOTE_CANCELLED: "Quote cancelled by user",
        TransactionState.DEPOSIT_PENDING: "Waiting for crypto deposit",
        TransactionState.DEPOSIT_DETECTED: "Deposit detected, awaiting confirmations",
        TransactionState.DEPOSIT_CONFIRMED: "Deposit confirmed, initiating settlement",
        TransactionState.DEPOSIT_FAILED: "Deposit failed (amount mismatch or other issue)",
        TransactionState.SETTLEMENT_PENDING: "Settlement pending",
        TransactionState.SETTLEMENT_PROCESSING: "Settlement being processed",
        TransactionState.SETTLEMENT_COMPLETED: "Settlement completed, initiating payout",
        TransactionState.SETTLEMENT_FAILED: "Settlement failed",
        TransactionState.PAYOUT_INITIATED: "Payout initiated to bank account",
        TransactionState.PAYOUT_PROCESSING: "Payout being processed",
        TransactionState.PAYOUT_COMPLETED: "Payout completed",
        TransactionState.PAYOUT_FAILED: "Payout failed",
        TransactionState.COMPLETED: "Transaction completed successfully",
        TransactionState.FAILED: "Transaction failed",
        TransactionState.REFUNDED: "Transaction refunded"
    }
    return descriptions.get(state, "Unknown state")

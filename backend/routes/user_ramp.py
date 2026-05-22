"""
User Ramp Routes - End-user UI endpoints for NeoNoble Ramp.

Provides off-ramp functionality powered by the PoR engine.
Users can access via JWT authentication (login).
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from pydantic import BaseModel, Field
import logging

from models.quote import QuoteResponse
from models.transaction import TransactionResponse
from services.ramp_service import RampService
from services.por_engine import InternalPoRProvider
from services.pricing_service import pricing_service, SUPPORTED_CRYPTOS, NENO_PRICE_EUR
from middleware.auth import get_current_user, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ramp", tags=["User Ramp"])

# Services will be set by main app
ramp_service: RampService = None
por_engine: InternalPoRProvider = None


def set_ramp_service(service: RampService):
    global ramp_service
    ramp_service = service


def set_por_engine(engine: InternalPoRProvider):
    global por_engine
    por_engine = engine


# ========================
# Request Models
# ========================

class UserQuoteRequest(BaseModel):
    fiat_amount: Optional[float] = None
    crypto_amount: Optional[float] = None
    crypto_currency: str


class UserRampRequest(BaseModel):
    quote_id: str
    wallet_address: Optional[str] = None
    bank_account: Optional[str] = None


class PoRQuoteRequest(BaseModel):
    """Request model for PoR-powered off-ramp quote."""
    crypto_amount: float = Field(..., gt=0, description="Amount of crypto to sell")
    crypto_currency: str = Field(default="NENO", description="Cryptocurrency symbol")
    bank_account: Optional[str] = Field(None, description="IBAN for payout")


class PoRExecuteRequest(BaseModel):
    """Request model for executing PoR off-ramp."""
    quote_id: str = Field(..., description="Quote ID to execute")
    bank_account: str = Field(..., description="IBAN for payout")


class PoRDepositRequest(BaseModel):
    """Request model for processing deposit (admin/internal)."""
    quote_id: str
    tx_hash: str
    amount: float


class PoROnRampQuoteRequest(BaseModel):
    """Request model for PoR-powered on-ramp quote."""
    fiat_amount: float = Field(..., gt=0, description="Amount of EUR to spend")
    crypto_currency: str = Field(default="NENO", description="Cryptocurrency to receive")
    wallet_address: Optional[str] = Field(None, description="Wallet address to receive crypto")


class PoROnRampExecuteRequest(BaseModel):
    """Request model for executing PoR on-ramp."""
    quote_id: str = Field(..., description="Quote ID to execute")
    wallet_address: str = Field(..., description="Wallet address to receive crypto")


class PoROnRampPaymentRequest(BaseModel):
    """Request model for processing on-ramp payment."""
    quote_id: str
    payment_ref: str
    amount_paid: float


# ========================
# Helper Functions
# ========================

def por_quote_to_response(quote) -> dict:
    """Convert PoR quote to API response."""
    response = {
        "quote_id": quote.quote_id,
        "provider": quote.provider.value,
        "direction": getattr(quote, 'direction', 'offramp'),
        "crypto_amount": quote.crypto_amount,
        "crypto_currency": quote.crypto_currency,
        "fiat_amount": quote.fiat_amount,
        "fiat_currency": quote.fiat_currency,
        "exchange_rate": quote.exchange_rate,
        "fee_amount": quote.fee_amount,
        "fee_percentage": quote.fee_percentage,
        "net_payout": quote.net_payout,
        "deposit_address": quote.deposit_address,
        "wallet_address": getattr(quote, 'wallet_address', None),
        "payment_reference": getattr(quote, 'payment_reference', None),
        "payment_amount": getattr(quote, 'payment_amount', None),
        "expires_at": quote.expires_at,
        "created_at": quote.created_at,
        "state": quote.state.value,
        "compliance": {
            "kyc_status": quote.compliance.kyc_status.value,
            "kyc_provider": quote.compliance.kyc_provider,
            "aml_status": quote.compliance.aml_status.value,
            "aml_provider": quote.compliance.aml_provider,
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
    return response


# ========================
# Price Endpoints
# ========================

@router.get("/prices")
async def get_prices():
    """Get current crypto prices in EUR."""
    try:
        prices = await pricing_service.get_all_prices_eur()
        return {
            "currency": "EUR",
            "prices": prices,
            "supported": SUPPORTED_CRYPTOS,
            "neno_fixed_price": NENO_PRICE_EUR
        }
    except Exception as e:
        logger.error(f"Failed to fetch prices: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch prices")


# ========================
# Legacy On-Ramp Endpoints
# ========================

@router.post("/onramp/quote", response_model=QuoteResponse)
async def create_onramp_quote(
    request: UserQuoteRequest,
    current_user: dict = Depends(get_optional_user)
):
    """Create an onramp quote (EUR -> Crypto) for logged-in users."""
    if not request.fiat_amount:
        raise HTTPException(status_code=400, detail="fiat_amount is required for onramp")
    
    if request.crypto_currency.upper() not in SUPPORTED_CRYPTOS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported cryptocurrency. Supported: {SUPPORTED_CRYPTOS}"
        )
    
    try:
        quote = await ramp_service.create_onramp_quote(
            fiat_amount=request.fiat_amount,
            crypto_currency=request.crypto_currency.upper()
        )
        return quote
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/onramp/execute", response_model=dict)
async def execute_onramp(
    request: UserRampRequest,
    current_user: dict = Depends(get_current_user)
):
    """Execute onramp transaction for logged-in users."""
    if not request.wallet_address:
        raise HTTPException(status_code=400, detail="wallet_address is required for onramp")
    
    result, error = await ramp_service.execute_onramp(
        quote_id=request.quote_id,
        wallet_address=request.wallet_address,
        user_id=current_user["user_id"]
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    return result.model_dump()


# ========================
# PoR-Powered On-Ramp Endpoints (User UI)
# ========================

@router.post("/onramp/por/quote")
async def create_onramp_quote_por(
    request: PoROnRampQuoteRequest,
    current_user: dict = Depends(get_optional_user)
):
    """
    Create an on-ramp quote powered by PoR engine.
    
    - NENO fixed price: €10,000
    - Fee: 1.5%
    - Returns payment reference for fiat payment
    - Returns full quote with compliance info
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not available")
    
    user_id = current_user.get("user_id") if current_user else None
    
    quote, error = await por_engine.create_onramp_quote(
        fiat_amount=request.fiat_amount,
        crypto_currency=request.crypto_currency,
        fiat_currency="EUR",
        user_id=user_id,
        wallet_address=request.wallet_address
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    return por_quote_to_response(quote)


@router.post("/onramp/por/execute")
async def execute_onramp_por(
    request: PoROnRampExecuteRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Accept and execute an on-ramp quote via PoR engine.
    
    Transitions quote to PAYMENT_PENDING state.
    User must then send fiat payment using the payment reference.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not available")
    
    quote, error = await por_engine.accept_onramp_quote(
        quote_id=request.quote_id,
        wallet_address=request.wallet_address
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    response = por_quote_to_response(quote)
    response["message"] = f"Please send €{quote.payment_amount} using reference: {quote.payment_reference}"
    
    return response


@router.post("/onramp/por/payment/process")
async def process_onramp_payment(
    request: PoROnRampPaymentRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Process a confirmed fiat payment (admin/internal use).
    
    In instant settlement mode, this will complete the entire
    on-ramp flow automatically.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not available")
    
    quote, error = await por_engine.process_onramp_payment(
        quote_id=request.quote_id,
        payment_ref=request.payment_ref,
        amount_paid=request.amount_paid
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    return por_quote_to_response(quote)


@router.get("/onramp/por/transaction/{quote_id}")
async def get_onramp_transaction(
    quote_id: str,
    current_user: dict = Depends(get_optional_user)
):
    """
    Get on-ramp transaction details by quote ID.
    
    Returns full transaction data including:
    - Current state
    - Compliance info (KYC/AML)
    - Timeline of all events
    - Crypto delivery details
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not available")
    
    quote = await por_engine.get_transaction(quote_id)
    
    if not quote:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    return por_quote_to_response(quote)


@router.get("/onramp/por/transaction/{quote_id}/timeline")
async def get_onramp_timeline(
    quote_id: str,
    current_user: dict = Depends(get_optional_user)
):
    """
    Get on-ramp transaction timeline (event history).
    
    Shows all state transitions from QUOTE_CREATED to COMPLETED.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not available")
    
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


# ========================
# PoR-Powered Off-Ramp Endpoints (User UI)
# ========================

@router.post("/offramp/quote")
async def create_offramp_quote_por(
    request: PoRQuoteRequest,
    current_user: dict = Depends(get_optional_user)
):
    """
    Create an off-ramp quote powered by PoR engine.
    
    - NENO fixed price: €10,000
    - Fee: 1.5%
    - Generates BSC deposit address
    - Returns full quote with compliance info
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not available")
    
    user_id = current_user.get("user_id") if current_user else None
    
    quote, error = await por_engine.create_quote(
        crypto_amount=request.crypto_amount,
        crypto_currency=request.crypto_currency,
        fiat_currency="EUR",
        user_id=user_id,
        bank_account=request.bank_account
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    return por_quote_to_response(quote)


@router.post("/offramp/execute")
async def execute_offramp_por(
    request: PoRExecuteRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Accept and execute an off-ramp quote via PoR engine.
    
    Transitions quote to DEPOSIT_PENDING state.
    User must then send crypto to the deposit address.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not available")
    
    quote, error = await por_engine.accept_quote(
        quote_id=request.quote_id,
        bank_account=request.bank_account
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    response = por_quote_to_response(quote)
    response["message"] = f"Please send {quote.crypto_amount} {quote.crypto_currency} to {quote.deposit_address}"
    
    return response


@router.get("/offramp/transaction/{quote_id}")
async def get_offramp_transaction(
    quote_id: str,
    current_user: dict = Depends(get_optional_user)
):
    """
    Get off-ramp transaction details by quote ID.
    
    Returns full transaction data including:
    - Current state
    - Compliance info (KYC/AML)
    - Timeline of all events
    - Settlement details
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not available")
    
    quote = await por_engine.get_transaction(quote_id)
    
    if not quote:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    return por_quote_to_response(quote)


@router.get("/offramp/transaction/{quote_id}/timeline")
async def get_offramp_timeline(
    quote_id: str,
    current_user: dict = Depends(get_optional_user)
):
    """
    Get off-ramp transaction timeline (event history).
    
    Shows all state transitions from QUOTE_CREATED to COMPLETED.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not available")
    
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


@router.get("/offramp/transactions")
async def list_offramp_transactions(
    state: Optional[str] = Query(None, description="Filter by state"),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    List user's off-ramp transactions.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not available")
    
    from services.provider_interface import TransactionState
    
    user_id = current_user.get("user_id")
    state_filter = TransactionState(state) if state else None
    
    transactions = await por_engine.list_transactions(
        user_id=user_id,
        state=state_filter,
        limit=limit
    )
    
    return {
        "count": len(transactions),
        "transactions": [por_quote_to_response(q) for q in transactions]
    }


# ========================
# Internal/Admin Endpoints
# ========================

@router.post("/offramp/deposit/process")
async def process_offramp_deposit(
    request: PoRDepositRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Process a confirmed crypto deposit (admin/internal use).
    
    In instant settlement mode, this will complete the entire
    off-ramp flow automatically.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not available")
    
    quote, error = await por_engine.process_deposit(
        quote_id=request.quote_id,
        tx_hash=request.tx_hash,
        amount=request.amount
    )
    
    if error:
        raise HTTPException(status_code=400, detail=error)
    
    return por_quote_to_response(quote)


# ========================
# Legacy Endpoints (backward compatibility)
# ========================

@router.get("/transactions", response_model=List[TransactionResponse])
async def get_transactions(current_user: dict = Depends(get_current_user)):
    """Get transaction history for logged-in user (legacy)."""
    transactions = await ramp_service.get_user_transactions(current_user["user_id"])
    return transactions

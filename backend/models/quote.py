from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class QuoteRequest(BaseModel):
    """Request for onramp or offramp quote"""
    fiat_currency: str = Field(default="EUR")
    fiat_amount: Optional[float] = Field(default=None, gt=0)
    crypto_currency: str = Field(..., description="Crypto currency code (BTC, ETH, NENO, etc.)")
    crypto_amount: Optional[float] = Field(default=None, gt=0)
    direction: Literal["onramp", "offramp"] = "onramp"


class QuoteResponse(BaseModel):
    """Quote response with calculated amounts"""
    quote_id: str
    direction: str
    fiat_currency: str
    fiat_amount: float
    crypto_currency: str
    crypto_amount: float
    exchange_rate: float  # Price of 1 crypto in fiat
    fee_amount: float
    fee_currency: str
    fee_percentage: float
    total_fiat: float  # fiat_amount + fee for onramp, fiat_amount - fee for offramp
    valid_until: datetime
    price_source: str  # "fixed" for NENO, "coingecko" for others
    deposit_address: Optional[str] = None  # For offramp: address to send crypto to


class RampRequest(BaseModel):
    """Execute ramp transaction"""
    quote_id: str
    wallet_address: Optional[str] = None  # Required for onramp
    bank_account: Optional[str] = None  # Required for offramp
    user_email: Optional[str] = None


class RampResponse(BaseModel):
    """Ramp transaction response"""
    transaction_id: str
    reference: str
    status: str
    direction: str
    fiat_currency: str
    fiat_amount: float
    crypto_currency: str
    crypto_amount: float
    exchange_rate: float
    fee_amount: float
    total_fiat: float
    wallet_address: Optional[str]
    bank_account: Optional[str]
    created_at: datetime
    message: str

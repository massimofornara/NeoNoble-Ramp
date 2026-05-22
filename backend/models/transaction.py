from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, timezone
from enum import Enum
import uuid


class TransactionType(str, Enum):
    ONRAMP = "ONRAMP"  # Fiat -> Crypto
    OFFRAMP = "OFFRAMP"  # Crypto -> Fiat


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Transaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None  # Can be null for API-initiated transactions
    api_key_id: Optional[str] = None  # For API-initiated transactions
    type: TransactionType
    fiat_currency: str = "EUR"
    fiat_amount: float
    crypto_currency: str
    crypto_amount: float
    exchange_rate: float
    fee_amount: float = 0.0
    fee_currency: str = "EUR"
    status: TransactionStatus = TransactionStatus.PENDING
    wallet_address: Optional[str] = None
    bank_account: Optional[str] = None
    reference: str = Field(default_factory=lambda: f"TX-{uuid.uuid4().hex[:12].upper()}")
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class TransactionCreate(BaseModel):
    type: TransactionType
    fiat_amount: float = Field(gt=0)
    crypto_currency: str
    wallet_address: Optional[str] = None
    bank_account: Optional[str] = None


class TransactionResponse(BaseModel):
    id: str
    type: TransactionType
    fiat_currency: str
    fiat_amount: float
    crypto_currency: str
    crypto_amount: float
    exchange_rate: float
    fee_amount: float
    status: TransactionStatus
    reference: str
    created_at: datetime
    completed_at: Optional[datetime]

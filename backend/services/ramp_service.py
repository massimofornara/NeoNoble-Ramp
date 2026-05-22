from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from enum import Enum
import logging
import uuid
import os
import asyncio

from models.transaction import (
    Transaction,
    TransactionCreate,
    TransactionResponse,
    TransactionType,
    TransactionStatus
)
from models.quote import QuoteRequest, QuoteResponse, RampRequest, RampResponse
from services.pricing_service import pricing_service

logger = logging.getLogger(__name__)

# Quote validity duration - configurable via environment variable
QUOTE_VALIDITY_MINUTES = int(os.environ.get('QUOTE_TTL_MINUTES', 5))


class QuoteStatus(str, Enum):
    """Status of a quote in the system."""
    AVAILABLE = "AVAILABLE"      # Quote can be confirmed
    LOCKED = "LOCKED"            # Quote is being processed (confirmation in progress)
    CONFIRMED = "CONFIRMED"      # Quote has been confirmed and transaction created
    EXPIRED = "EXPIRED"          # Quote has expired (TTL exceeded)
    RECEIVED = "RECEIVED"        # Crypto deposit received on-chain
    COMPLETED = "COMPLETED"      # Payout completed


class QuoteEntry:
    """Represents a cached quote with its status and metadata."""
    
    def __init__(self, quote: QuoteResponse, expires_at: datetime):
        self.quote = quote
        self.expires_at = expires_at
        self.status = QuoteStatus.AVAILABLE
        self.locked_at: Optional[datetime] = None
        self.confirmed_at: Optional[datetime] = None
        self.received_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.transaction_id: Optional[str] = None
        self.deposit_address: Optional[str] = None
        self.deposit_tx_hash: Optional[str] = None
        self.payout_id: Optional[str] = None
        self._lock = asyncio.Lock()
    
    def is_expired(self) -> bool:
        """Check if the quote has expired based on TTL."""
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_available(self) -> bool:
        """Check if the quote is available for confirmation."""
        return self.status == QuoteStatus.AVAILABLE and not self.is_expired()
    
    async def try_lock(self) -> tuple[bool, Optional[str]]:
        """Attempt to lock the quote for processing."""
        async with self._lock:
            if self.is_expired():
                self.status = QuoteStatus.EXPIRED
                return False, "Quote has expired"
            
            if self.status == QuoteStatus.LOCKED:
                return False, "Quote is already being processed"
            
            if self.status in [QuoteStatus.CONFIRMED, QuoteStatus.RECEIVED, QuoteStatus.COMPLETED]:
                return False, "Quote has already been confirmed"
            
            if self.status == QuoteStatus.EXPIRED:
                return False, "Quote has expired"
            
            self.status = QuoteStatus.LOCKED
            self.locked_at = datetime.now(timezone.utc)
            logger.info(f"Quote {self.quote.quote_id} locked for processing")
            return True, None
    
    async def confirm(self, transaction_id: str, deposit_address: str = None) -> None:
        """Mark the quote as confirmed with the associated transaction."""
        async with self._lock:
            self.status = QuoteStatus.CONFIRMED
            self.confirmed_at = datetime.now(timezone.utc)
            self.transaction_id = transaction_id
            self.deposit_address = deposit_address
            logger.info(f"Quote {self.quote.quote_id} confirmed with transaction {transaction_id}")
    
    async def mark_received(self, tx_hash: str) -> None:
        """Mark the quote as having received the crypto deposit."""
        async with self._lock:
            self.status = QuoteStatus.RECEIVED
            self.received_at = datetime.now(timezone.utc)
            self.deposit_tx_hash = tx_hash
            logger.info(f"Quote {self.quote.quote_id} received deposit (tx: {tx_hash})")
    
    async def mark_completed(self, payout_id: str = None) -> None:
        """Mark the quote as completed (payout initiated)."""
        async with self._lock:
            self.status = QuoteStatus.COMPLETED
            self.completed_at = datetime.now(timezone.utc)
            self.payout_id = payout_id
            logger.info(f"Quote {self.quote.quote_id} completed (payout: {payout_id})")
    
    async def unlock(self) -> None:
        """Release the lock (e.g., if processing failed)."""
        async with self._lock:
            if self.status == QuoteStatus.LOCKED:
                self.status = QuoteStatus.AVAILABLE
                self.locked_at = None
                logger.info(f"Quote {self.quote.quote_id} unlocked")


# In-memory quote cache (in production, use Redis with distributed locks)
_quote_cache: dict[str, QuoteEntry] = {}


class RampService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.transactions
        self._wallet_service = None
        self._blockchain_listener = None
        self._payout_service = None
    
    def set_wallet_service(self, wallet_service):
        """Set the wallet service for address generation."""
        self._wallet_service = wallet_service
    
    def set_blockchain_listener(self, listener):
        """Set the blockchain listener."""
        self._blockchain_listener = listener
    
    def set_payout_service(self, payout_service):
        """Set the payout service."""
        self._payout_service = payout_service
    
    async def create_onramp_quote(self, fiat_amount: float, crypto_currency: str) -> QuoteResponse:
        """Create an onramp quote (Fiat -> Crypto)."""
        quote_data = await pricing_service.calculate_onramp_quote(
            fiat_amount=fiat_amount,
            crypto=crypto_currency
        )
        
        quote_id = f"quote_{uuid.uuid4().hex[:16]}"
        valid_until = datetime.now(timezone.utc) + timedelta(minutes=QUOTE_VALIDITY_MINUTES)
        
        quote = QuoteResponse(
            quote_id=quote_id,
            direction="onramp",
            valid_until=valid_until,
            **quote_data
        )
        
        _quote_cache[quote_id] = QuoteEntry(quote=quote, expires_at=valid_until)
        
        logger.info(f"Created onramp quote: {quote_id} - {fiat_amount} EUR -> {quote.crypto_amount} {crypto_currency}")
        return quote
    
    async def create_offramp_quote(self, crypto_amount: float, crypto_currency: str) -> QuoteResponse:
        """Create an offramp quote (Crypto -> Fiat)."""
        quote_data = await pricing_service.calculate_offramp_quote(
            crypto_amount=crypto_amount,
            crypto=crypto_currency
        )
        
        quote_id = f"quote_{uuid.uuid4().hex[:16]}"
        valid_until = datetime.now(timezone.utc) + timedelta(minutes=QUOTE_VALIDITY_MINUTES)
        
        # For offramp, generate a deposit address if wallet service is available
        deposit_address = None
        if self._wallet_service and crypto_currency.upper() == "NENO":
            address, error = await self._wallet_service.generate_deposit_address(quote_id)
            if address:
                deposit_address = address
                logger.info(f"Generated deposit address for quote {quote_id}: {address}")
            elif error:
                logger.warning(f"Could not generate deposit address: {error}")
        
        quote = QuoteResponse(
            quote_id=quote_id,
            direction="offramp",
            valid_until=valid_until,
            deposit_address=deposit_address,  # Include deposit address in response
            **quote_data
        )
        
        # Store quote with deposit address
        entry = QuoteEntry(quote=quote, expires_at=valid_until)
        entry.deposit_address = deposit_address
        _quote_cache[quote_id] = entry
        
        logger.info(f"Created offramp quote: {quote_id} - {crypto_amount} {crypto_currency} -> {quote.fiat_amount} EUR")
        return quote
    
    async def get_offramp_quote_with_address(self, quote_id: str) -> Optional[dict]:
        """Get offramp quote details including deposit address."""
        entry = _quote_cache.get(quote_id)
        if not entry:
            return None
        
        return {
            "quote_id": quote_id,
            "quote": entry.quote.model_dump(),
            "deposit_address": entry.deposit_address,
            "status": entry.status.value,
            "expires_at": entry.expires_at.isoformat()
        }
    
    def _get_quote_entry(self, quote_id: str) -> tuple[Optional[QuoteEntry], Optional[str]]:
        """Get a quote entry from cache with validation."""
        entry = _quote_cache.get(quote_id)
        if not entry:
            return None, "Quote not found or expired"
        return entry, None
    
    async def execute_onramp(
        self,
        quote_id: str,
        wallet_address: str,
        user_id: Optional[str] = None,
        api_key_id: Optional[str] = None
    ) -> tuple[Optional[RampResponse], Optional[str]]:
        """Execute an onramp transaction with quote locking."""
        
        entry, error = self._get_quote_entry(quote_id)
        if error:
            return None, error
        
        quote = entry.quote
        
        if quote.direction != "onramp":
            return None, "Invalid quote type for onramp"
        
        if not wallet_address:
            return None, "Wallet address is required for onramp"
        
        lock_success, lock_error = await entry.try_lock()
        if not lock_success:
            logger.warning(f"Failed to lock quote {quote_id}: {lock_error}")
            return None, lock_error
        
        try:
            transaction = Transaction(
                user_id=user_id,
                api_key_id=api_key_id,
                type=TransactionType.ONRAMP,
                fiat_currency=quote.fiat_currency,
                fiat_amount=quote.fiat_amount,
                crypto_currency=quote.crypto_currency,
                crypto_amount=quote.crypto_amount,
                exchange_rate=quote.exchange_rate,
                fee_amount=quote.fee_amount,
                fee_currency=quote.fee_currency,
                wallet_address=wallet_address,
                status=TransactionStatus.PROCESSING,
                metadata={"quote_id": quote_id}
            )
            
            tx_dict = transaction.model_dump()
            for field in ['created_at', 'updated_at', 'completed_at']:
                if tx_dict.get(field):
                    tx_dict[field] = tx_dict[field].isoformat()
            await self.collection.insert_one(tx_dict)
            
            await entry.confirm(transaction.id)
            await self._complete_transaction(transaction.id)
            
            logger.info(f"Executed onramp: {transaction.reference} - {quote.total_fiat} EUR -> {quote.crypto_amount} {quote.crypto_currency}")
            
            return RampResponse(
                transaction_id=transaction.id,
                reference=transaction.reference,
                status=TransactionStatus.PROCESSING.value,
                direction="onramp",
                fiat_currency=quote.fiat_currency,
                fiat_amount=quote.fiat_amount,
                crypto_currency=quote.crypto_currency,
                crypto_amount=quote.crypto_amount,
                exchange_rate=quote.exchange_rate,
                fee_amount=quote.fee_amount,
                total_fiat=quote.total_fiat,
                wallet_address=wallet_address,
                bank_account=None,
                created_at=transaction.created_at,
                message="Transaction initiated. Crypto will be sent to your wallet once payment is confirmed."
            ), None
            
        except Exception as e:
            await entry.unlock()
            logger.error(f"Failed to execute onramp for quote {quote_id}: {e}")
            return None, f"Transaction failed: {str(e)}"
    
    async def execute_offramp(
        self,
        quote_id: str,
        bank_account: str,
        user_id: Optional[str] = None,
        api_key_id: Optional[str] = None
    ) -> tuple[Optional[RampResponse], Optional[str]]:
        """Execute an offramp transaction with quote locking and deposit address."""
        
        entry, error = self._get_quote_entry(quote_id)
        if error:
            return None, error
        
        quote = entry.quote
        
        if quote.direction != "offramp":
            return None, "Invalid quote type for offramp"
        
        if not bank_account:
            return None, "Bank account is required for offramp"
        
        lock_success, lock_error = await entry.try_lock()
        if not lock_success:
            logger.warning(f"Failed to lock quote {quote_id}: {lock_error}")
            return None, lock_error
        
        try:
            # Get or generate deposit address for NENO
            deposit_address = entry.deposit_address
            if not deposit_address and self._wallet_service and quote.crypto_currency == "NENO":
                deposit_address, addr_error = await self._wallet_service.generate_deposit_address(quote_id)
                if addr_error:
                    logger.warning(f"Could not generate deposit address: {addr_error}")
            
            transaction = Transaction(
                user_id=user_id,
                api_key_id=api_key_id,
                type=TransactionType.OFFRAMP,
                fiat_currency=quote.fiat_currency,
                fiat_amount=quote.fiat_amount,
                crypto_currency=quote.crypto_currency,
                crypto_amount=quote.crypto_amount,
                exchange_rate=quote.exchange_rate,
                fee_amount=quote.fee_amount,
                fee_currency=quote.fee_currency,
                bank_account=bank_account,
                wallet_address=deposit_address,  # Now includes deposit address!
                status=TransactionStatus.PENDING,  # Waiting for crypto deposit
                metadata={
                    "quote_id": quote_id,
                    "deposit_address": deposit_address,
                    "awaiting_deposit": True
                }
            )
            
            tx_dict = transaction.model_dump()
            for field in ['created_at', 'updated_at', 'completed_at']:
                if tx_dict.get(field):
                    tx_dict[field] = tx_dict[field].isoformat()
            await self.collection.insert_one(tx_dict)
            
            await entry.confirm(transaction.id, deposit_address)
            
            # For NENO offramp, we wait for deposit - don't complete yet
            if quote.crypto_currency == "NENO" and deposit_address:
                message = (
                    f"Please send exactly {quote.crypto_amount} NENO to the deposit address. "
                    f"Funds will be converted to EUR and sent to your bank account after confirmation."
                )
            else:
                # For non-NENO or when no deposit address, complete immediately (legacy flow)
                await self._complete_transaction(transaction.id)
                message = "Transaction initiated. Funds will be sent to your bank account once crypto is received."
            
            logger.info(f"Executed offramp: {transaction.reference} - {quote.crypto_amount} {quote.crypto_currency} -> {quote.total_fiat} EUR")
            
            return RampResponse(
                transaction_id=transaction.id,
                reference=transaction.reference,
                status=TransactionStatus.PENDING.value if deposit_address else TransactionStatus.PROCESSING.value,
                direction="offramp",
                fiat_currency=quote.fiat_currency,
                fiat_amount=quote.fiat_amount,
                crypto_currency=quote.crypto_currency,
                crypto_amount=quote.crypto_amount,
                exchange_rate=quote.exchange_rate,
                fee_amount=quote.fee_amount,
                total_fiat=quote.total_fiat,
                wallet_address=deposit_address,  # Return the deposit address!
                bank_account=bank_account,
                created_at=transaction.created_at,
                message=message
            ), None
            
        except Exception as e:
            await entry.unlock()
            logger.error(f"Failed to execute offramp for quote {quote_id}: {e}")
            return None, f"Transaction failed: {str(e)}"
    
    async def process_deposit_received(
        self,
        quote_id: str,
        tx_hash: str,
        amount_received: float
    ) -> tuple[bool, Optional[str]]:
        """
        Process a confirmed crypto deposit.
        
        Called by the blockchain listener when deposit is confirmed.
        """
        entry = _quote_cache.get(quote_id)
        if not entry:
            return False, "Quote not found"
        
        if entry.status not in [QuoteStatus.CONFIRMED, QuoteStatus.LOCKED]:
            return False, f"Quote in invalid state: {entry.status}"
        
        # Update quote status
        await entry.mark_received(tx_hash)
        
        # Update transaction in database
        await self.collection.update_one(
            {"metadata.quote_id": quote_id},
            {
                "$set": {
                    "status": TransactionStatus.PROCESSING.value,
                    "metadata.deposit_tx_hash": tx_hash,
                    "metadata.deposit_amount": amount_received,
                    "metadata.deposit_confirmed_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        # Trigger payout
        if self._payout_service:
            tx_doc = await self.collection.find_one({"metadata.quote_id": quote_id})
            if tx_doc:
                payout_amount = entry.quote.total_fiat
                payout_result, payout_error = await self._payout_service.create_payout(
                    quote_id=quote_id,
                    transaction_id=tx_doc["id"],
                    amount_eur=payout_amount,
                    reference=tx_doc["reference"]
                )
                
                if payout_result:
                    payout_id = payout_result.get("payout_id")
                    await entry.mark_completed(payout_id)
                    
                    # Update transaction as completed
                    await self.collection.update_one(
                        {"metadata.quote_id": quote_id},
                        {
                            "$set": {
                                "status": TransactionStatus.COMPLETED.value,
                                "metadata.payout_id": payout_id,
                                "completed_at": datetime.now(timezone.utc).isoformat(),
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }
                        }
                    )
                    
                    logger.info(f"Offramp completed for quote {quote_id}: payout {payout_id}")
                    return True, None
                else:
                    logger.error(f"Payout failed for quote {quote_id}: {payout_error}")
                    return False, payout_error
        
        return True, None
    
    async def get_active_offramp_quotes(self) -> List[dict]:
        """
        Get all active offramp quotes awaiting deposits.
        
        Used by the blockchain listener.
        """
        active_quotes = []
        
        for quote_id, entry in _quote_cache.items():
            if (entry.quote.direction == "offramp" and 
                entry.status in [QuoteStatus.CONFIRMED, QuoteStatus.LOCKED] and
                entry.deposit_address and
                not entry.is_expired()):
                
                active_quotes.append({
                    "quote_id": quote_id,
                    "address": entry.deposit_address,
                    "expected_amount": entry.quote.crypto_amount,
                    "crypto_currency": entry.quote.crypto_currency
                })
        
        return active_quotes
    
    async def get_quote_status(self, quote_id: str) -> Optional[dict]:
        """Get the current status of a quote."""
        entry = _quote_cache.get(quote_id)
        if not entry:
            return None
        
        return {
            "quote_id": quote_id,
            "status": entry.status.value,
            "is_expired": entry.is_expired(),
            "is_available": entry.is_available(),
            "locked_at": entry.locked_at.isoformat() if entry.locked_at else None,
            "confirmed_at": entry.confirmed_at.isoformat() if entry.confirmed_at else None,
            "received_at": entry.received_at.isoformat() if entry.received_at else None,
            "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
            "transaction_id": entry.transaction_id,
            "deposit_address": entry.deposit_address,
            "deposit_tx_hash": entry.deposit_tx_hash,
            "payout_id": entry.payout_id,
            "expires_at": entry.expires_at.isoformat()
        }
    
    async def _complete_transaction(self, transaction_id: str):
        """Mark a transaction as completed (simulation for non-blockchain flow)."""
        await self.collection.update_one(
            {"id": transaction_id},
            {
                "$set": {
                    "status": TransactionStatus.COMPLETED.value,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
    
    async def get_user_transactions(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[TransactionResponse]:
        """Get transactions for a user."""
        transactions = []
        cursor = self.collection.find(
            {"user_id": user_id}
        ).sort("created_at", -1).limit(limit)
        
        async for doc in cursor:
            tx = self._doc_to_response(doc)
            transactions.append(tx)
        
        return transactions
    
    def _doc_to_response(self, doc: dict) -> TransactionResponse:
        """Convert MongoDB document to TransactionResponse."""
        for field in ['created_at', 'updated_at', 'completed_at']:
            if doc.get(field) and isinstance(doc[field], str):
                doc[field] = datetime.fromisoformat(doc[field])
        
        return TransactionResponse(
            id=doc['id'],
            type=doc['type'],
            fiat_currency=doc['fiat_currency'],
            fiat_amount=doc['fiat_amount'],
            crypto_currency=doc['crypto_currency'],
            crypto_amount=doc['crypto_amount'],
            exchange_rate=doc['exchange_rate'],
            fee_amount=doc['fee_amount'],
            status=doc['status'],
            reference=doc['reference'],
            created_at=doc['created_at'],
            completed_at=doc.get('completed_at')
        )

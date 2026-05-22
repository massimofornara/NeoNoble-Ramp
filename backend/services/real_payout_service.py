"""
Real Payout Service for NeoNoble Ramp.

Handles real EUR payouts via Stripe to configured bank accounts (SEPA)
and cards (instant payout fallback).

Payout Flow:
1. NENO deposit confirmed → Calculate EUR payout
2. Create Stripe Payout to pre-configured external bank account
3. Monitor via webhooks (payout.paid, payout.failed)
4. If SEPA fails, fallback to card payout (if enabled)
5. Update PoR transaction state based on payout status

Environment Variables Required:
- STRIPE_SECRET_KEY: Stripe API secret key
- STRIPE_WEBHOOK_SECRET: Webhook signing secret
- PAYOUT_IBAN: Destination IBAN for SEPA transfers
- PAYOUT_BENEFICIARY_NAME: Beneficiary name
- PAYOUT_CURRENCY: Currency (default: EUR)
- PAYOUT_MODE: 'standard' or 'instant' (default: standard)
- PAYOUT_CARD_ENABLED: Enable card fallback (true/false)
- PAYOUT_CARD_TOKEN: Stripe card token for instant payout fallback
"""

import os
import logging
from typing import Optional, Dict, Tuple, List
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass
import stripe
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


class PayoutStatus(Enum):
    """Payout status enum."""
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    PAID = "paid"
    FAILED = "failed"
    CANCELED = "canceled"
    REQUIRES_FALLBACK = "requires_fallback"


class PayoutMethod(Enum):
    """Payout method enum."""
    SEPA = "sepa"
    CARD = "card"
    MANUAL = "manual"


@dataclass
class PayoutConfig:
    """Payout configuration."""
    iban: str
    beneficiary_name: str
    currency: str = "EUR"
    mode: str = "standard"  # 'standard' or 'instant'
    card_enabled: bool = False
    card_token: Optional[str] = None
    webhook_secret: Optional[str] = None


@dataclass
class PayoutResult:
    """Result of a payout operation."""
    success: bool
    payout_id: Optional[str] = None
    status: Optional[PayoutStatus] = None
    method: Optional[PayoutMethod] = None
    provider_reference: Optional[str] = None
    arrival_date: Optional[str] = None
    error: Optional[str] = None
    details: Optional[Dict] = None


class RealPayoutService:
    """
    Real payout service using Stripe Payouts API.
    
    Supports:
    - SEPA Credit Transfers (primary method)
    - Instant Card Payouts (fallback)
    - Webhook-based status updates
    - Full audit trail integration
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.payouts_collection = db.real_payouts
        self._initialized = False
        self._stripe_configured = False
        self._config: Optional[PayoutConfig] = None
        self._external_account_id: Optional[str] = None
        self._card_id: Optional[str] = None
    
    def _load_config(self) -> PayoutConfig:
        """Load payout configuration from environment."""
        return PayoutConfig(
            iban=os.environ.get('PAYOUT_IBAN', os.environ.get('STRIPE_PAYOUT_IBAN', '')),
            beneficiary_name=os.environ.get('PAYOUT_BENEFICIARY_NAME', os.environ.get('STRIPE_PAYOUT_BENEFICIARY_NAME', '')),
            currency=os.environ.get('PAYOUT_CURRENCY', 'EUR'),
            mode=os.environ.get('PAYOUT_MODE', 'standard'),
            card_enabled=os.environ.get('PAYOUT_CARD_ENABLED', 'false').lower() == 'true',
            card_token=os.environ.get('PAYOUT_CARD_TOKEN'),
            webhook_secret=os.environ.get('STRIPE_WEBHOOK_SECRET')
        )
    
    def _initialize_stripe(self) -> bool:
        """Initialize Stripe SDK."""
        if self._stripe_configured:
            return True
        
        api_key = os.environ.get('STRIPE_SECRET_KEY')
        if not api_key:
            logger.error("STRIPE_SECRET_KEY not configured. Real payouts are DISABLED.")
            return False
        
        stripe.api_key = api_key
        self._stripe_configured = True
        self._config = self._load_config()
        
        logger.info(
            f"Stripe Payout Service initialized:\n"
            f"  Mode: {self._config.mode.upper()}\n"
            f"  Beneficiary: {self._config.beneficiary_name}\n"
            f"  IBAN: {self._config.iban[:8]}...{self._config.iban[-4:]}\n"
            f"  Currency: {self._config.currency}\n"
            f"  Card Fallback: {'Enabled' if self._config.card_enabled else 'Disabled'}"
        )
        return True
    
    async def initialize(self):
        """Initialize the payout service and create indexes."""
        if self._initialized:
            return
        
        # Create indexes
        try:
            await self.payouts_collection.create_index("payout_id", unique=True, sparse=True)
            await self.payouts_collection.create_index("quote_id")
            await self.payouts_collection.create_index("status")
            await self.payouts_collection.create_index("created_at")
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")
        
        # Initialize Stripe
        if not self._initialize_stripe():
            logger.warning("Stripe not initialized - payouts will fail")
            return
        
        # Check Stripe account status
        await self._verify_stripe_account()
        
        self._initialized = True
        logger.info("Real Payout Service initialized successfully")
    
    async def _verify_stripe_account(self):
        """Verify Stripe account and capabilities."""
        try:
            # Check account
            account = stripe.Account.retrieve()
            logger.info(f"Stripe Account: {account.id} ({account.country})")
            
            # Check balance
            balance = stripe.Balance.retrieve()
            eur_balance = 0
            for b in balance.available:
                if b.currency == 'eur':
                    eur_balance = b.amount / 100
            logger.info(f"Stripe EUR Balance: €{eur_balance:,.2f}")
            
            # Check if payouts are enabled
            if hasattr(account, 'payouts_enabled'):
                if account.payouts_enabled:
                    logger.info("Stripe Payouts: ENABLED")
                else:
                    logger.warning("Stripe Payouts: DISABLED - Check account settings")
            
        except stripe.error.StripeError as e:
            logger.warning(f"Could not verify Stripe account: {e}")
    
    def is_available(self) -> bool:
        """Check if payout service is available."""
        return self._initialize_stripe()
    
    async def create_payout(
        self,
        quote_id: str,
        transaction_id: str,
        amount_eur: float,
        reference: str = None,
        metadata: Dict = None
    ) -> PayoutResult:
        """
        Create a real payout to the configured IBAN.
        
        Args:
            quote_id: The quote ID from PoR engine
            transaction_id: Internal transaction ID
            amount_eur: Amount in EUR to payout
            reference: Optional payment reference
            metadata: Additional metadata for audit trail
            
        Returns:
            PayoutResult with payout details or error
        """
        if not self._initialize_stripe():
            return PayoutResult(
                success=False,
                error="Stripe not configured"
            )
        
        reference = reference or f"NENO-{quote_id[:8]}"
        
        # Check for duplicate
        existing = await self.payouts_collection.find_one({
            'quote_id': quote_id,
            'status': {'$in': ['pending', 'in_transit', 'paid']}
        })
        
        if existing:
            logger.warning(f"Payout already exists for quote {quote_id}")
            return PayoutResult(
                success=True,
                payout_id=existing.get('payout_id'),
                status=PayoutStatus(existing.get('status', 'pending')),
                method=PayoutMethod(existing.get('method', 'sepa')),
                provider_reference=existing.get('provider_reference'),
                details=existing
            )
        
        # Create payout record
        payout_record = {
            'quote_id': quote_id,
            'transaction_id': transaction_id,
            'amount_eur': amount_eur,
            'amount_cents': int(amount_eur * 100),
            'reference': reference,
            'iban': self._config.iban,
            'beneficiary_name': self._config.beneficiary_name,
            'currency': self._config.currency,
            'mode': self._config.mode,
            'method': None,
            'status': PayoutStatus.PENDING.value,
            'payout_id': None,
            'provider_reference': None,
            'arrival_date': None,
            'error': None,
            'failure_code': None,
            'failure_message': None,
            'stripe_response': None,
            'metadata': metadata or {},
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Try SEPA payout first
        result = await self._create_sepa_payout(payout_record, amount_eur, reference)
        
        # If SEPA failed and card fallback is enabled, try card payout
        if not result.success and self._config.card_enabled and self._config.card_token:
            logger.info(f"SEPA payout failed, attempting card fallback for quote {quote_id}")
            result = await self._create_card_payout(payout_record, amount_eur, reference)
        
        return result
    
    async def _create_sepa_payout(
        self,
        payout_record: Dict,
        amount_eur: float,
        reference: str
    ) -> PayoutResult:
        """Create a SEPA payout via Stripe."""
        try:
            logger.info(f"Creating SEPA payout: €{amount_eur:,.2f} to {self._config.iban[:8]}...")
            
            # Create Stripe Payout
            # Note: This creates a payout from your Stripe balance to your connected bank account
            payout = stripe.Payout.create(
                amount=int(amount_eur * 100),  # Amount in cents
                currency=self._config.currency.lower(),
                description=f"NeoNoble Off-Ramp: {reference}",
                statement_descriptor="NEONOBLE",
                method="standard" if self._config.mode == "standard" else "instant",
                metadata={
                    'quote_id': payout_record['quote_id'],
                    'transaction_id': payout_record['transaction_id'],
                    'beneficiary': self._config.beneficiary_name,
                    'iban_prefix': self._config.iban[:8],
                    'reference': reference,
                    'source': 'neonoble_ramp_por'
                }
            )
            
            # Update payout record
            payout_record['payout_id'] = payout.id
            payout_record['method'] = PayoutMethod.SEPA.value
            payout_record['status'] = payout.status
            payout_record['provider_reference'] = payout.id
            payout_record['arrival_date'] = datetime.fromtimestamp(payout.arrival_date, timezone.utc).isoformat() if payout.arrival_date else None
            payout_record['stripe_response'] = {
                'id': payout.id,
                'object': payout.object,
                'status': payout.status,
                'amount': payout.amount,
                'currency': payout.currency,
                'arrival_date': payout.arrival_date,
                'method': payout.method,
                'type': payout.type,
                'created': payout.created
            }
            payout_record['updated_at'] = datetime.now(timezone.utc).isoformat()
            
            # Store in database
            await self.payouts_collection.insert_one(payout_record)
            
            logger.info(
                f"✅ SEPA Payout CREATED: {payout.id}\n"
                f"   Amount: €{amount_eur:,.2f}\n"
                f"   Status: {payout.status}\n"
                f"   Arrival: {payout_record['arrival_date']}"
            )
            
            return PayoutResult(
                success=True,
                payout_id=payout.id,
                status=PayoutStatus(payout.status) if payout.status in [s.value for s in PayoutStatus] else PayoutStatus.PENDING,
                method=PayoutMethod.SEPA,
                provider_reference=payout.id,
                arrival_date=payout_record['arrival_date'],
                details={
                    'stripe_payout_id': payout.id,
                    'amount_eur': amount_eur,
                    'currency': payout.currency,
                    'method': 'sepa',
                    'arrival_date': payout_record['arrival_date']
                }
            )
            
        except stripe.error.InvalidRequestError as e:
            error_msg = str(e)
            logger.error(f"Stripe InvalidRequestError: {error_msg}")
            payout_record['status'] = PayoutStatus.FAILED.value
            payout_record['error'] = error_msg
            payout_record['method'] = PayoutMethod.SEPA.value
            await self.payouts_collection.insert_one(payout_record)
            
            return PayoutResult(
                success=False,
                status=PayoutStatus.REQUIRES_FALLBACK,
                method=PayoutMethod.SEPA,
                error=error_msg
            )
            
        except stripe.error.StripeError as e:
            error_msg = str(e)
            logger.error(f"Stripe Error creating SEPA payout: {error_msg}")
            payout_record['status'] = PayoutStatus.FAILED.value
            payout_record['error'] = error_msg
            payout_record['method'] = PayoutMethod.SEPA.value
            await self.payouts_collection.insert_one(payout_record)
            
            return PayoutResult(
                success=False,
                status=PayoutStatus.REQUIRES_FALLBACK,
                method=PayoutMethod.SEPA,
                error=error_msg
            )
    
    async def _create_card_payout(
        self,
        payout_record: Dict,
        amount_eur: float,
        reference: str
    ) -> PayoutResult:
        """Create an instant card payout via Stripe (fallback)."""
        if not self._config.card_token:
            return PayoutResult(
                success=False,
                error="Card token not configured for fallback"
            )
        
        try:
            logger.info(f"Creating Card Payout (fallback): €{amount_eur:,.2f}")
            
            # Create instant payout to card
            payout = stripe.Payout.create(
                amount=int(amount_eur * 100),
                currency=self._config.currency.lower(),
                description=f"NeoNoble Off-Ramp (Card): {reference}",
                statement_descriptor="NEONOBLE",
                method="instant",  # Card payouts are instant
                destination=self._config.card_token,
                metadata={
                    'quote_id': payout_record['quote_id'],
                    'transaction_id': payout_record['transaction_id'],
                    'reference': reference,
                    'source': 'neonoble_ramp_por',
                    'fallback': 'true'
                }
            )
            
            # Update existing failed record or create new
            payout_record['payout_id'] = payout.id
            payout_record['method'] = PayoutMethod.CARD.value
            payout_record['status'] = payout.status
            payout_record['provider_reference'] = payout.id
            payout_record['stripe_response'] = {
                'id': payout.id,
                'status': payout.status,
                'amount': payout.amount,
                'method': 'instant',
                'created': payout.created
            }
            payout_record['updated_at'] = datetime.now(timezone.utc).isoformat()
            payout_record['error'] = None  # Clear previous error
            
            # Update in database (upsert)
            await self.payouts_collection.update_one(
                {'quote_id': payout_record['quote_id']},
                {'$set': payout_record},
                upsert=True
            )
            
            logger.info(f"✅ Card Payout CREATED (fallback): {payout.id} - €{amount_eur:,.2f}")
            
            return PayoutResult(
                success=True,
                payout_id=payout.id,
                status=PayoutStatus(payout.status) if payout.status in [s.value for s in PayoutStatus] else PayoutStatus.PENDING,
                method=PayoutMethod.CARD,
                provider_reference=payout.id,
                details={
                    'stripe_payout_id': payout.id,
                    'amount_eur': amount_eur,
                    'method': 'card',
                    'fallback': True
                }
            )
            
        except stripe.error.StripeError as e:
            error_msg = str(e)
            logger.error(f"Card payout also failed: {error_msg}")
            
            return PayoutResult(
                success=False,
                status=PayoutStatus.FAILED,
                method=PayoutMethod.CARD,
                error=f"Both SEPA and Card payouts failed: {error_msg}"
            )
    
    async def handle_webhook(
        self,
        payload: bytes,
        sig_header: str
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Handle Stripe webhook events for payout status updates.
        
        Returns:
            Tuple of (success, error_message, event_data)
        """
        if not self._config or not self._config.webhook_secret:
            logger.warning("Webhook secret not configured")
            return False, "Webhook secret not configured", None
        
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self._config.webhook_secret
            )
        except ValueError as e:
            logger.error(f"Invalid webhook payload: {e}")
            return False, "Invalid payload", None
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid webhook signature: {e}")
            return False, "Invalid signature", None
        
        event_type = event['type']
        payout_data = event['data']['object']
        
        logger.info(f"Received Stripe webhook: {event_type}")
        
        result_data = None
        
        if event_type == 'payout.paid':
            result_data = await self._handle_payout_paid(payout_data)
        elif event_type == 'payout.failed':
            result_data = await self._handle_payout_failed(payout_data)
        elif event_type == 'payout.canceled':
            result_data = await self._handle_payout_canceled(payout_data)
        elif event_type == 'payout.created':
            logger.info(f"Payout created: {payout_data['id']}")
        elif event_type == 'payout.updated':
            result_data = await self._handle_payout_updated(payout_data)
        
        return True, None, result_data
    
    async def _handle_payout_paid(self, payout_data: dict) -> Dict:
        """Handle payout.paid webhook - payout was successful."""
        payout_id = payout_data['id']
        
        update_data = {
            'status': PayoutStatus.PAID.value,
            'paid_at': datetime.now(timezone.utc).isoformat(),
            'arrival_date': datetime.fromtimestamp(payout_data.get('arrival_date', 0), timezone.utc).isoformat() if payout_data.get('arrival_date') else None,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        result = await self.payouts_collection.find_one_and_update(
            {'payout_id': payout_id},
            {'$set': update_data},
            return_document=True
        )
        
        if result:
            logger.info(
                f"✅ Payout PAID: {payout_id}\n"
                f"   Quote: {result.get('quote_id')}\n"
                f"   Amount: €{result.get('amount_eur'):,.2f}"
            )
            return {
                'event': 'payout.paid',
                'quote_id': result.get('quote_id'),
                'payout_id': payout_id,
                'amount_eur': result.get('amount_eur')
            }
        else:
            logger.warning(f"Payout {payout_id} not found in database")
            return {'event': 'payout.paid', 'payout_id': payout_id, 'status': 'not_found'}
    
    async def _handle_payout_failed(self, payout_data: dict) -> Dict:
        """Handle payout.failed webhook - payout failed."""
        payout_id = payout_data['id']
        failure_code = payout_data.get('failure_code', 'unknown')
        failure_message = payout_data.get('failure_message', 'Payout failed')
        
        update_data = {
            'status': PayoutStatus.FAILED.value,
            'failure_code': failure_code,
            'failure_message': failure_message,
            'error': failure_message,
            'failed_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        result = await self.payouts_collection.find_one_and_update(
            {'payout_id': payout_id},
            {'$set': update_data},
            return_document=True
        )
        
        if result:
            logger.error(
                f"❌ Payout FAILED: {payout_id}\n"
                f"   Quote: {result.get('quote_id')}\n"
                f"   Reason: {failure_code} - {failure_message}"
            )
            
            # If card fallback is enabled and this was a SEPA payout, trigger fallback
            if (self._config.card_enabled and 
                self._config.card_token and 
                result.get('method') == PayoutMethod.SEPA.value):
                logger.info(f"Triggering card fallback for quote {result.get('quote_id')}")
                # Card fallback will be triggered by PoR engine when it processes the webhook
            
            return {
                'event': 'payout.failed',
                'quote_id': result.get('quote_id'),
                'payout_id': payout_id,
                'failure_code': failure_code,
                'failure_message': failure_message,
                'method': result.get('method'),
                'requires_fallback': (
                    self._config.card_enabled and 
                    result.get('method') == PayoutMethod.SEPA.value
                )
            }
        else:
            logger.warning(f"Failed payout {payout_id} not found in database")
            return {'event': 'payout.failed', 'payout_id': payout_id, 'status': 'not_found'}
    
    async def _handle_payout_canceled(self, payout_data: dict) -> Dict:
        """Handle payout.canceled webhook."""
        payout_id = payout_data['id']
        
        await self.payouts_collection.update_one(
            {'payout_id': payout_id},
            {
                '$set': {
                    'status': PayoutStatus.CANCELED.value,
                    'canceled_at': datetime.now(timezone.utc).isoformat(),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        logger.warning(f"Payout CANCELED: {payout_id}")
        return {'event': 'payout.canceled', 'payout_id': payout_id}
    
    async def _handle_payout_updated(self, payout_data: dict) -> Dict:
        """Handle payout.updated webhook."""
        payout_id = payout_data['id']
        new_status = payout_data.get('status', 'unknown')
        
        await self.payouts_collection.update_one(
            {'payout_id': payout_id},
            {
                '$set': {
                    'status': new_status,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        logger.info(f"Payout UPDATED: {payout_id} → {new_status}")
        return {'event': 'payout.updated', 'payout_id': payout_id, 'status': new_status}
    
    async def get_payout_by_quote(self, quote_id: str) -> Optional[Dict]:
        """Get payout record by quote ID."""
        doc = await self.payouts_collection.find_one(
            {'quote_id': quote_id},
            {'_id': 0}
        )
        return doc
    
    async def get_payout_status(self, payout_id: str) -> Optional[Dict]:
        """Get payout status from Stripe."""
        if not self._initialize_stripe():
            return None
        
        try:
            payout = stripe.Payout.retrieve(payout_id)
            return {
                'payout_id': payout.id,
                'status': payout.status,
                'amount': payout.amount / 100,
                'currency': payout.currency,
                'arrival_date': datetime.fromtimestamp(payout.arrival_date, timezone.utc).isoformat() if payout.arrival_date else None,
                'failure_code': payout.failure_code,
                'failure_message': payout.failure_message
            }
        except stripe.error.StripeError as e:
            logger.error(f"Error fetching payout {payout_id}: {e}")
            return None
    
    async def list_payouts(
        self,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """List recent payouts."""
        query = {}
        if status:
            query['status'] = status
        
        cursor = self.payouts_collection.find(
            query, {'_id': 0}
        ).sort('created_at', -1).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def get_payout_summary(self) -> Dict:
        """Get summary statistics for payouts."""
        pipeline = [
            {
                '$group': {
                    '_id': '$status',
                    'count': {'$sum': 1},
                    'total_eur': {'$sum': '$amount_eur'}
                }
            }
        ]
        
        results = await self.payouts_collection.aggregate(pipeline).to_list(length=20)
        
        # Check Stripe balance
        eur_balance = 0
        if self._initialize_stripe():
            try:
                balance = stripe.Balance.retrieve()
                for b in balance.available:
                    if b.currency == 'eur':
                        eur_balance = b.amount / 100
            except Exception:
                pass
        
        return {
            'by_status': {r['_id']: {'count': r['count'], 'total_eur': r['total_eur']} for r in results},
            'stripe_balance_eur': eur_balance,
            'config': {
                'mode': self._config.mode if self._config else 'not_configured',
                'card_fallback_enabled': self._config.card_enabled if self._config else False,
                'currency': self._config.currency if self._config else 'EUR'
            }
        }


# Global service instance
_real_payout_service: Optional[RealPayoutService] = None


def get_real_payout_service() -> Optional[RealPayoutService]:
    """Get global real payout service instance."""
    return _real_payout_service


def set_real_payout_service(service: RealPayoutService):
    """Set global real payout service instance."""
    global _real_payout_service
    _real_payout_service = service

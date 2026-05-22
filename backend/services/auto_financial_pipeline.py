"""
Autonomous Financial Pipeline — NeoNoble Ramp.

Fully automated money loop:
  User Deposit (Stripe) → Fee Extraction → Revenue Accumulation → Auto-Payout (SEPA)

Zero manual intervention. Self-executing pipeline.
"""

import logging
import os
import uuid
import asyncio
import stripe
from datetime import datetime, timezone, timedelta
from enum import Enum

from database.mongodb import get_database

logger = logging.getLogger("auto_pipeline")

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

AUTO_PAYOUT_THRESHOLD_EUR = 10.0
AUTO_PAYOUT_CHECK_INTERVAL_SECONDS = 120  # Check every 2 minutes
PLATFORM_FEE_RATE = 0.02  # 2% platform fee on deposits


class PipelineStatus(str, Enum):
    INITIATED = "initiated"
    FUNDED = "funded"
    PAYOUT_PROCESSING = "payout_processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AutonomousFinancialPipeline:
    """
    Self-executing financial engine.
    Routes user EUR deposits through Stripe, extracts fees,
    and auto-triggers SEPA payouts when balance is sufficient.
    """

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.running = False
        self.cycle_count = 0
        self.last_check = None
        self.last_payout = None
        self.total_funded = 0
        self.total_paid_out = 0

    # ── USER DEPOSIT VIA STRIPE ──

    async def create_deposit_intent(self, user_id: str, amount_eur: float, user_email: str = "") -> dict:
        """
        Create a Stripe PaymentIntent for user EUR deposit.
        When paid, funds go directly to Stripe balance → available for payouts.
        """
        if not stripe.api_key:
            return {"error": "Stripe non configurato"}

        db = get_database()
        deposit_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Calculate fee
        fee_eur = round(amount_eur * PLATFORM_FEE_RATE, 2)
        net_credit = round(amount_eur - fee_eur, 2)

        try:
            # Find or create Stripe customer
            customer_id = await self._get_or_create_customer(user_id, user_email)

            # Create PaymentIntent
            intent = stripe.PaymentIntent.create(
                amount=int(amount_eur * 100),
                currency="eur",
                customer=customer_id,
                payment_method_types=["card", "sepa_debit"],
                description=f"NeoNoble Deposit #{deposit_id[:8]}",
                statement_descriptor_suffix="NEONOBLE",
                metadata={
                    "type": "user_deposit",
                    "deposit_id": deposit_id,
                    "user_id": user_id,
                    "fee_eur": str(fee_eur),
                    "net_credit_eur": str(net_credit),
                },
            )

            # Track in DB
            await db.deposit_pipeline.update_one(
                {"_id": deposit_id},
                {"$setOnInsert": {
                    "deposit_id": deposit_id,
                    "user_id": user_id,
                    "amount_eur": amount_eur,
                    "fee_eur": fee_eur,
                    "net_credit_eur": net_credit,
                    "stripe_payment_intent_id": intent.id,
                    "stripe_client_secret": intent.client_secret,
                    "stripe_customer_id": customer_id,
                    "status": PipelineStatus.INITIATED,
                    "created_at": now.isoformat(),
                }},
                upsert=True,
            )

            logger.info(f"[PIPELINE] Deposit intent created: {deposit_id} | {amount_eur} EUR | PI: {intent.id}")

            return {
                "deposit_id": deposit_id,
                "client_secret": intent.client_secret,
                "payment_intent_id": intent.id,
                "amount_eur": amount_eur,
                "fee_eur": fee_eur,
                "net_credit_eur": net_credit,
                "status": PipelineStatus.INITIATED,
            }

        except stripe.error.StripeError as e:
            logger.error(f"[PIPELINE] Deposit intent error: {e}")
            return {"error": str(e.user_message)}

    async def _get_or_create_customer(self, user_id: str, email: str) -> str:
        """Get or create a Stripe customer for the user."""
        db = get_database()
        mapping = await db.stripe_customers.find_one({"user_id": user_id})
        if mapping:
            return mapping["stripe_customer_id"]

        try:
            customer = stripe.Customer.create(
                email=email or f"user_{user_id[:8]}@neonoble.com",
                metadata={"user_id": user_id, "platform": "neonoble_ramp"},
            )
            await db.stripe_customers.update_one(
                {"user_id": user_id},
                {"$set": {"stripe_customer_id": customer.id, "created_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
            return customer.id
        except Exception as e:
            logger.error(f"[PIPELINE] Customer creation error: {e}")
            raise

    # ── WEBHOOK HANDLERS ──

    async def handle_payment_succeeded(self, payment_intent_id: str) -> dict:
        """
        Called when payment_intent.succeeded webhook fires.
        Credits user wallet + extracts fee to revenue.
        """
        db = get_database()
        deposit = await db.deposit_pipeline.find_one(
            {"stripe_payment_intent_id": payment_intent_id}, {"_id": 0}
        )
        if not deposit:
            logger.warning(f"[PIPELINE] Unknown PI: {payment_intent_id}")
            return {"handled": False}

        if deposit.get("status") == PipelineStatus.FUNDED:
            return {"handled": True, "already_processed": True}

        user_id = deposit["user_id"]
        net_credit = deposit["net_credit_eur"]
        fee_eur = deposit["fee_eur"]
        deposit_id = deposit["deposit_id"]

        # Credit user EUR wallet
        await db.wallets.update_one(
            {"user_id": user_id, "asset": "EUR"},
            {"$inc": {"balance": net_credit}},
            upsert=True,
        )

        # Update pipeline status
        now = datetime.now(timezone.utc)
        await db.deposit_pipeline.update_one(
            {"deposit_id": deposit_id},
            {"$set": {
                "status": PipelineStatus.FUNDED,
                "funded_at": now.isoformat(),
                "stripe_funded": True,
            }},
        )

        # Log revenue event
        await db.revenue_events.update_one(
            {"_id": f"dep_fee_{deposit_id}"},
            {"$setOnInsert": {
                "source": "deposit_fee",
                "amount": fee_eur,
                "currency": "EUR",
                "user_id": user_id,
                "deposit_id": deposit_id,
                "metadata": {"payment_intent": payment_intent_id},
                "created_at": now.isoformat(),
            }},
            upsert=True,
        )

        self.total_funded += deposit["amount_eur"]
        logger.info(f"[PIPELINE] Deposit funded: {deposit_id} | Credit: {net_credit} EUR | Fee: {fee_eur} EUR")

        return {
            "handled": True,
            "deposit_id": deposit_id,
            "user_credited": net_credit,
            "fee_extracted": fee_eur,
            "status": PipelineStatus.FUNDED,
        }

    async def handle_payout_paid(self, payout_id: str) -> dict:
        """Called when payout.paid webhook fires."""
        db = get_database()
        now = datetime.now(timezone.utc)

        await db.sepa_payouts.update_one(
            {"payout_id": payout_id},
            {"$set": {"status": "paid", "paid_at": now.isoformat()}},
        )

        # Also update any pipeline entries
        await db.auto_payout_log.update_one(
            {"payout_id": payout_id},
            {"$set": {"status": "paid", "paid_at": now.isoformat()}},
        )

        self.total_paid_out += 1
        logger.info(f"[PIPELINE] Payout confirmed paid: {payout_id}")

        return {"handled": True, "payout_id": payout_id, "status": "paid"}

    async def handle_balance_available(self) -> dict:
        """Called when balance.available webhook fires. Triggers auto-payout check."""
        return await self.check_and_auto_payout()

    # ── AUTO-PAYOUT ENGINE ──

    async def check_and_auto_payout(self) -> dict:
        """
        Check Stripe balance and auto-execute SEPA payout if above threshold.
        Called by background loop AND by balance.available webhook.
        """
        if not stripe.api_key:
            return {"executed": False, "reason": "no_stripe_key"}

        try:
            bal = stripe.Balance.retrieve()
            eur_available = 0
            for b in bal.available:
                if b.currency == "eur":
                    eur_available = b.amount / 100
        except Exception as e:
            logger.error(f"[AUTO-PAYOUT] Balance check error: {e}")
            return {"executed": False, "reason": str(e)}

        self.last_check = datetime.now(timezone.utc).isoformat()

        if eur_available < AUTO_PAYOUT_THRESHOLD_EUR:
            return {
                "executed": False,
                "reason": "below_threshold",
                "balance_eur": eur_available,
                "threshold_eur": AUTO_PAYOUT_THRESHOLD_EUR,
            }

        # Execute auto-payout
        payout_amount = eur_available  # Payout entire available balance
        try:
            payout = stripe.Payout.create(
                amount=int(payout_amount * 100),
                currency="eur",
                description=f"NeoNoble Auto-Payout #{self.cycle_count}",
                statement_descriptor="NEONOBLE",
                method="standard",
                metadata={
                    "type": "auto_payout",
                    "cycle": str(self.cycle_count),
                    "triggered_by": "autonomous_pipeline",
                },
            )

            # Log in DB
            db = get_database()
            now = datetime.now(timezone.utc)
            payout_log_id = str(uuid.uuid4())
            await db.auto_payout_log.update_one(
                {"_id": payout_log_id},
                {"$setOnInsert": {
                    "payout_id": payout.id,
                    "amount_eur": payout_amount,
                    "status": payout.status,
                    "method": payout.method,
                    "cycle": self.cycle_count,
                    "triggered_by": "autonomous_pipeline",
                    "created_at": now.isoformat(),
                }},
                upsert=True,
            )

            # Also track in sepa_payouts
            await db.sepa_payouts.update_one(
                {"payout_id": payout.id},
                {"$setOnInsert": {
                    "payout_id": payout.id,
                    "amount_eur": payout_amount,
                    "status": payout.status,
                    "method": "auto",
                    "admin_email": "autonomous_pipeline",
                    "created_at": now.isoformat(),
                }},
                upsert=True,
            )

            self.last_payout = now.isoformat()
            self.total_paid_out += payout_amount
            logger.info(f"[AUTO-PAYOUT] Executed: {payout.id} | €{payout_amount:.2f} | Status: {payout.status}")

            return {
                "executed": True,
                "payout_id": payout.id,
                "amount_eur": payout_amount,
                "status": payout.status,
                "status_flow": "pending → in_transit → paid",
            }

        except stripe.error.StripeError as e:
            logger.error(f"[AUTO-PAYOUT] Payout error: {e.user_message}")
            return {"executed": False, "reason": str(e.user_message), "balance_eur": eur_available}

    # ── INTERNAL AUTO-FUND (from revenue ledger to Stripe) ──

    async def auto_fund_from_revenue(self) -> dict:
        """
        When real revenue exists in internal ledger but not yet in Stripe,
        creates a PaymentIntent to move funds.
        Uses the platform admin's stored payment method if available.
        """
        db = get_database()

        # Calculate unfunded revenue
        rev_agg = await db.revenue_events.aggregate([
            {"$match": {"stripe_funded": {"$ne": True}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        unfunded = rev_agg[0] if rev_agg else {}
        unfunded_amount = unfunded.get("total", 0)

        if unfunded_amount < 1:
            return {"funded": False, "reason": "no_unfunded_revenue", "unfunded_eur": unfunded_amount}

        # Check if platform has a stored payment method
        admin_user = await db.users.find_one({"role": "ADMIN"})
        if not admin_user:
            return {"funded": False, "reason": "no_admin_user"}

        admin_id = admin_user.get("id", "")
        customer_mapping = await db.stripe_customers.find_one({"user_id": admin_id})

        if not customer_mapping:
            # Create customer for admin
            try:
                customer = stripe.Customer.create(
                    email=admin_user.get("email", "admin@neonoble.com"),
                    metadata={"user_id": admin_id, "role": "admin", "platform": "neonoble"},
                )
                customer_id = customer.id
                await db.stripe_customers.update_one(
                    {"user_id": admin_id},
                    {"$set": {"stripe_customer_id": customer_id, "created_at": datetime.now(timezone.utc).isoformat()}},
                    upsert=True,
                )
            except Exception as e:
                return {"funded": False, "reason": f"customer_creation_failed: {e}"}
        else:
            customer_id = customer_mapping["stripe_customer_id"]

        # Check for stored payment methods
        try:
            methods = stripe.PaymentMethod.list(customer=customer_id, type="card", limit=1)
            if not methods.data:
                # Try SEPA
                methods = stripe.PaymentMethod.list(customer=customer_id, type="sepa_debit", limit=1)
        except Exception:
            methods = type('obj', (object,), {'data': []})()

        if methods.data:
            # Auto-charge using stored method
            pm = methods.data[0]
            try:
                intent = stripe.PaymentIntent.create(
                    amount=int(unfunded_amount * 100),
                    currency="eur",
                    customer=customer_id,
                    payment_method=pm.id,
                    off_session=True,
                    confirm=True,
                    description="NeoNoble Auto-Fund Revenue",
                    metadata={"type": "auto_fund", "revenue_amount": str(unfunded_amount)},
                )

                if intent.status == "succeeded":
                    # Mark revenue events as funded
                    await db.revenue_events.update_many(
                        {"stripe_funded": {"$ne": True}},
                        {"$set": {"stripe_funded": True, "funded_at": datetime.now(timezone.utc).isoformat()}},
                    )
                    self.total_funded += unfunded_amount
                    logger.info(f"[AUTO-FUND] Charged {unfunded_amount} EUR via stored method {pm.id}")
                    return {
                        "funded": True,
                        "amount_eur": unfunded_amount,
                        "payment_intent": intent.id,
                        "method": "stored_payment_method",
                    }
            except Exception as e:
                logger.warning(f"[AUTO-FUND] Stored method charge failed: {e}")

        # Fallback: Create PaymentIntent for manual completion via UI
        try:
            intent = stripe.PaymentIntent.create(
                amount=int(unfunded_amount * 100),
                currency="eur",
                customer=customer_id,
                payment_method_types=["card", "sepa_debit"],
                description="NeoNoble Revenue Auto-Fund",
                metadata={"type": "auto_fund_pending", "revenue_amount": str(unfunded_amount)},
            )
            return {
                "funded": False,
                "pending_intent": True,
                "payment_intent_id": intent.id,
                "client_secret": intent.client_secret,
                "amount_eur": unfunded_amount,
                "reason": "no_stored_payment_method",
                "action": "Completare il pagamento nel dashboard o aggiungere un metodo di pagamento",
            }
        except Exception as e:
            return {"funded": False, "reason": str(e)}

    # ── BACKGROUND LOOP ──

    async def start_background_loop(self):
        """Start the autonomous pipeline background monitor."""
        if self.running:
            return
        self.running = True
        logger.info(f"[PIPELINE] Autonomous Financial Pipeline started (threshold: €{AUTO_PAYOUT_THRESHOLD_EUR})")

        while self.running:
            try:
                self.cycle_count += 1
                result = await self.check_and_auto_payout()
                if result.get("executed"):
                    logger.info(f"[PIPELINE] Cycle {self.cycle_count}: Auto-payout executed: {result}")
            except Exception as e:
                logger.error(f"[PIPELINE] Cycle {self.cycle_count} error: {e}")

            await asyncio.sleep(AUTO_PAYOUT_CHECK_INTERVAL_SECONDS)

    def stop(self):
        self.running = False

    async def get_status(self) -> dict:
        """Get pipeline status."""
        db = get_database()

        # Pending deposits
        pending = await db.deposit_pipeline.count_documents({"status": PipelineStatus.INITIATED})
        funded = await db.deposit_pipeline.count_documents({"status": PipelineStatus.FUNDED})
        total_deposits = await db.deposit_pipeline.count_documents({})

        # Auto payouts
        auto_payouts = await db.auto_payout_log.count_documents({})
        paid_payouts = await db.auto_payout_log.count_documents({"status": "paid"})

        # Stripe balance (cached check)
        stripe_eur = 0
        try:
            bal = stripe.Balance.retrieve()
            for b in bal.available:
                if b.currency == "eur":
                    stripe_eur = b.amount / 100
        except Exception:
            pass

        return {
            "running": self.running,
            "cycle_count": self.cycle_count,
            "last_check": self.last_check,
            "last_payout": self.last_payout,
            "auto_payout_threshold_eur": AUTO_PAYOUT_THRESHOLD_EUR,
            "stripe_balance_eur": stripe_eur,
            "payout_ready": stripe_eur >= AUTO_PAYOUT_THRESHOLD_EUR,
            "deposits": {
                "total": total_deposits,
                "pending": pending,
                "funded": funded,
            },
            "payouts": {
                "total": auto_payouts,
                "paid": paid_payouts,
            },
            "totals": {
                "funded_eur": self.total_funded,
                "paid_out": self.total_paid_out,
            },
        }

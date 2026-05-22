"""
Autonomous Pipeline & Stripe Webhook Routes — NeoNoble Ramp.

Handles:
- Stripe webhook events (payment_intent.succeeded, payout.paid, balance.available)
- Pipeline status & control
- User deposit flow
- Auto-fund trigger
"""

import os
import logging
import stripe
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from routes.auth import get_current_user
from services.auto_financial_pipeline import AutonomousFinancialPipeline

logger = logging.getLogger("pipeline_routes")

router = APIRouter(tags=["Autonomous Pipeline"])


# ── STRIPE WEBHOOKS ──

STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint. Handles:
    - payment_intent.succeeded → credits user + marks funded
    - payout.paid → marks payout complete
    - balance.available → triggers auto-payout check
    - charge.succeeded → logs charge
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    event = None
    if STRIPE_WEBHOOK_SECRET:
        if not sig_header:
            logger.warning("[WEBHOOK] Missing stripe-signature header")
            raise HTTPException(status_code=400, detail="Missing stripe-signature header")
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            logger.error(f"[WEBHOOK] Signature verification failed: {e}")
            raise HTTPException(status_code=400, detail="Invalid signature")
    else:
        import json
        try:
            event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid payload")

    pipeline = AutonomousFinancialPipeline.get_instance()
    event_type = event.get("type", "") if isinstance(event, dict) else event.type

    logger.info(f"[WEBHOOK] Received: {event_type}")

    result = {"received": True, "type": event_type}

    if event_type == "payment_intent.succeeded":
        pi_id = event.data.object.id if hasattr(event, 'data') else event["data"]["object"]["id"]
        result.update(await pipeline.handle_payment_succeeded(pi_id))

    elif event_type == "payout.paid":
        payout_id = event.data.object.id if hasattr(event, 'data') else event["data"]["object"]["id"]
        result.update(await pipeline.handle_payout_paid(payout_id))

    elif event_type == "payout.failed":
        payout_id = event.data.object.id if hasattr(event, 'data') else event["data"]["object"]["id"]
        logger.error(f"[WEBHOOK] Payout FAILED: {payout_id}")
        from database.mongodb import get_database
        db = get_database()
        await db.sepa_payouts.update_one(
            {"payout_id": payout_id},
            {"$set": {"status": "failed", "failed_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}},
        )
        result["payout_failed"] = payout_id

    elif event_type == "balance.available":
        result.update(await pipeline.handle_balance_available())

    elif event_type == "charge.succeeded":
        logger.info("[WEBHOOK] Charge succeeded")

    return result


# ── PIPELINE CONTROL ──

@router.get("/pipeline/status")
async def pipeline_status(current_user: dict = Depends(get_current_user)):
    """Get autonomous pipeline status."""
    pipeline = AutonomousFinancialPipeline.get_instance()
    return await pipeline.get_status()


@router.post("/pipeline/auto-payout-check")
async def trigger_auto_payout(current_user: dict = Depends(get_current_user)):
    """Manually trigger auto-payout check (admin)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    pipeline = AutonomousFinancialPipeline.get_instance()
    return await pipeline.check_and_auto_payout()


@router.post("/pipeline/auto-fund")
async def trigger_auto_fund(current_user: dict = Depends(get_current_user)):
    """Trigger auto-funding from revenue ledger to Stripe (admin)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    pipeline = AutonomousFinancialPipeline.get_instance()
    return await pipeline.auto_fund_from_revenue()


# ── USER DEPOSIT ──

class DepositRequest(BaseModel):
    amount_eur: float


@router.post("/pipeline/deposit")
async def create_deposit(req: DepositRequest, current_user: dict = Depends(get_current_user)):
    """
    Create a Stripe-powered EUR deposit.
    Returns client_secret for Stripe Elements / Checkout completion.
    Funds go directly to platform Stripe balance.
    """
    if req.amount_eur < 1:
        raise HTTPException(status_code=400, detail="Minimo 1 EUR")

    pipeline = AutonomousFinancialPipeline.get_instance()
    result = await pipeline.create_deposit_intent(
        user_id=current_user["user_id"],
        amount_eur=req.amount_eur,
        user_email=current_user.get("email", ""),
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


# ── PIPELINE HISTORY ──

@router.get("/pipeline/deposits")
async def deposit_history(limit: int = 50, current_user: dict = Depends(get_current_user)):
    """User's deposit history."""
    from database.mongodb import get_database
    db = get_database()
    deposits = await db.deposit_pipeline.find(
        {"user_id": current_user["user_id"]},
        {"_id": 0, "stripe_client_secret": 0},
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"deposits": deposits, "count": len(deposits)}


@router.get("/pipeline/payouts")
async def payout_history(limit: int = 50, current_user: dict = Depends(get_current_user)):
    """Auto-payout history (admin)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    from database.mongodb import get_database
    db = get_database()
    payouts = await db.auto_payout_log.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"payouts": payouts, "count": len(payouts)}

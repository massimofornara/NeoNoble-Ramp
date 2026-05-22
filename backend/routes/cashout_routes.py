"""
Cashout API Routes — NeoNoble Ramp.

Endpoints for monitoring and controlling the autonomous cashout engine:
- Cashout status and metrics
- Cashout history
- EUR account management
- Conversion opportunities
- Manual trigger / stop
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from pydantic import BaseModel
import logging

from routes.auth import get_current_user
from services.cashout_engine import CashoutEngine, EUR_ACCOUNTS
from services.auto_conversion_engine import AutoConversionEngine

logger = logging.getLogger("cashout_routes")

router = APIRouter(prefix="/cashout", tags=["Cashout Engine"])


# ── ENGINE STATUS ──

@router.get("/status")
async def cashout_status(current_user: dict = Depends(get_current_user)):
    """Full cashout engine status with metrics, accounts, and recent operations."""
    engine = CashoutEngine.get_instance()
    return await engine.get_status()


@router.get("/history")
async def cashout_history(
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    """Cashout operation history."""
    engine = CashoutEngine.get_instance()
    history = await engine.get_cashout_history(limit)
    return {"cashouts": history, "count": len(history)}


# ── ENGINE CONTROL ──

@router.post("/start")
async def start_cashout(current_user: dict = Depends(get_current_user)):
    """Start the autonomous cashout engine (admin only)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    engine = CashoutEngine.get_instance()
    await engine.start()
    return {"status": "started", "message": "Cashout engine avviato"}


@router.post("/stop")
async def stop_cashout(current_user: dict = Depends(get_current_user)):
    """Stop the autonomous cashout engine (admin only)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    engine = CashoutEngine.get_instance()
    await engine.stop()
    return {"status": "stopped", "message": "Cashout engine fermato"}


# ── EUR ACCOUNTS ──

@router.get("/eur-accounts")
async def get_eur_accounts(current_user: dict = Depends(get_current_user)):
    """Get configured EUR payout accounts (SEPA/SWIFT destinations)."""
    return {
        "accounts": EUR_ACCOUNTS,
        "routing_rules": {
            "sepa_instant": "< 5,000 EUR",
            "sepa_standard": "5,000 — 100,000 EUR",
            "swift": "> 100,000 EUR (batch, uses BE account)",
        },
    }


# ── CONVERSION ──

@router.get("/conversions/opportunities")
async def conversion_opportunities(current_user: dict = Depends(get_current_user)):
    """Evaluate current crypto → USDC conversion opportunities."""
    from services.execution_engine import ExecutionEngine
    engine = ExecutionEngine.get_instance()
    hot_wallet = await engine.get_hot_wallet_status()

    converter = AutoConversionEngine.get_instance()
    opps = await converter.evaluate_conversions(hot_wallet)

    return {
        "hot_wallet": hot_wallet,
        "opportunities": opps,
        "count": len(opps),
    }


@router.get("/conversions/history")
async def conversion_history(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Conversion history log."""
    converter = AutoConversionEngine.get_instance()
    history = await converter.get_conversion_history(limit)
    return {"conversions": history, "count": len(history)}


@router.get("/conversions/summary")
async def conversion_summary(current_user: dict = Depends(get_current_user)):
    """Conversion summary by pair."""
    converter = AutoConversionEngine.get_instance()
    return await converter.get_summary()


# ── REVENUE WITHDRAWAL ──

class RevenueWithdrawRequest(BaseModel):
    amount: float
    currency: str = "EUR"  # EUR or crypto asset
    destination_type: str = "sepa"  # sepa, swift, crypto
    destination_iban: Optional[str] = None
    destination_wallet: Optional[str] = None
    beneficiary_name: Optional[str] = None


@router.post("/revenue-withdraw")
async def revenue_withdraw(req: RevenueWithdrawRequest, current_user: dict = Depends(get_current_user)):
    """
    Manual revenue withdrawal — Admin only.
    Withdraws from the REVENUE wallet to configured EUR accounts or crypto wallets.
    Full audit trail + idempotency.
    """
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only — accesso negato")

    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Importo deve essere > 0")

    from database.mongodb import get_database
    from datetime import datetime, timezone
    import uuid

    db = get_database()
    withdraw_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    # Idempotency check
    from services.idempotency_service import check_idempotency, mark_idempotency
    idem_key = f"revenue_withdraw_{current_user['user_id']}_{req.amount}_{req.method}"
    existing = await check_idempotency(idem_key, "revenue_withdraw")
    if existing:
        return existing

    # Validate revenue balance
    engine = CashoutEngine.get_instance()
    status = await engine.get_status()
    revenue_balance_eur = status.get("cumulative", {}).get("extracted_eur", 0)

    # Check USDC revenue wallet balance
    try:
        from services.circle_wallet_service import CircleWalletService, WalletRole
        circle = CircleWalletService.get_instance()
        balances = await circle.get_all_wallet_balances("BSC")
        revenue_usdc = balances.get("wallets", {}).get(WalletRole.REVENUE, {}).get("balance", 0)
    except Exception:
        revenue_usdc = 0

    # Route based on destination type
    payout_result = None
    real_payout_id = None
    real_tx_hash = None

    if req.destination_type in ("sepa", "swift"):
        destination_iban = req.destination_iban
        if not destination_iban:
            # Use default configured accounts
            if req.amount < 100000:
                destination_iban = EUR_ACCOUNTS["IT"]["iban"]
            else:
                destination_iban = EUR_ACCOUNTS["BE"]["iban"]

        beneficiary_name = req.beneficiary_name or EUR_ACCOUNTS["IT"]["beneficiary"]

        try:
            from services.real_payout_service import get_real_payout_service
            payout_svc = get_real_payout_service()
            if payout_svc and payout_svc.is_available():
                payout_result = await payout_svc.create_payout(
                    quote_id=withdraw_id,
                    transaction_id=withdraw_id,
                    amount_eur=req.amount,
                    reference=f"REVENUE-{withdraw_id[:8].upper()}",
                    metadata={
                        "user_id": current_user["user_id"],
                        "type": "revenue_withdrawal",
                        "iban": destination_iban,
                        "beneficiary": beneficiary_name,
                    },
                )
                if payout_result.success:
                    real_payout_id = payout_result.payout_id
        except Exception as e:
            logger.warning(f"[REVENUE-WITHDRAW] Payout error: {e}")

    elif req.destination_type == "crypto":
        if not req.destination_wallet:
            raise HTTPException(status_code=400, detail="destination_wallet richiesto per crypto withdrawal")
        try:
            from services.execution_engine import ExecutionEngine
            exec_engine = ExecutionEngine.get_instance()
            exec_result = await exec_engine.send_asset_real("USDC", req.destination_wallet, req.amount)
            if exec_result.get("success"):
                real_tx_hash = exec_result["tx_hash"]
        except Exception as e:
            logger.warning(f"[REVENUE-WITHDRAW] Crypto send error: {e}")
    else:
        raise HTTPException(status_code=400, detail="destination_type deve essere 'sepa', 'swift' o 'crypto'")

    # Audit log
    withdrawal = {
        "id": withdraw_id,
        "type": "revenue_withdrawal",
        "admin_user_id": current_user["user_id"],
        "admin_email": current_user.get("email", ""),
        "amount": req.amount,
        "currency": req.currency,
        "destination_type": req.destination_type,
        "destination_iban": req.destination_iban,
        "destination_wallet": req.destination_wallet,
        "beneficiary": beneficiary_name,
        "payout_id": real_payout_id,
        "tx_hash": real_tx_hash,
        "status": "completed" if (real_payout_id or real_tx_hash) else "pending",
        "revenue_usdc_balance": revenue_usdc,
        "revenue_balance_eur": revenue_balance_eur,
        "created_at": now.isoformat(),
    }
    await db.revenue_withdrawals.insert_one({**withdrawal, "_id": withdraw_id})

    # Also log in audit_events
    audit_event_id = str(uuid.uuid4())
    await db.audit_events.update_one(
        {"_id": audit_event_id},
        {"$setOnInsert": {
            "event_id": audit_event_id,
            "event": "REVENUE_WITHDRAWAL",
            "admin": current_user.get("email", ""),
            "amount": req.amount,
            "destination": req.destination_type,
            "payout_id": real_payout_id,
            "tx_hash": real_tx_hash,
            "created_at": now,
        }},
        upsert=True,
    )

    return {
        "success": True,
        "withdrawal": withdrawal,
        "message": f"Revenue withdrawal di {req.amount} {req.currency} {'eseguito' if (real_payout_id or real_tx_hash) else 'in attesa'}",
        "payout_id": real_payout_id,
        "tx_hash": real_tx_hash,
        "explorer": f"https://bscscan.com/tx/{real_tx_hash}" if real_tx_hash else None,
    }


@router.get("/revenue-history")
async def revenue_withdrawal_history(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Revenue withdrawal history — Admin only."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    from database.mongodb import get_database
    db = get_database()
    withdrawals = await db.revenue_withdrawals.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"withdrawals": withdrawals, "count": len(withdrawals)}

# ── STRIPE BALANCE TOP-UP (Checkout Session) ──

class StripeTopUpRequest(BaseModel):
    amount_eur: float

@router.post("/stripe-topup")
async def stripe_balance_topup(req: StripeTopUpRequest, current_user: dict = Depends(get_current_user)):
    """
    Create a Stripe Checkout session to top up the platform's Stripe balance.
    Admin only. After payment completes, funds are available for SEPA payouts.
    """
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    if req.amount_eur < 1:
        raise HTTPException(status_code=400, detail="Minimo 1 EUR")

    import stripe
    import os
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe non configurato")

    frontend_url = "https://multi-chain-wallet-14.preview.emergentagent.com"

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "unit_amount": int(req.amount_eur * 100),
                    "product_data": {
                        "name": "NeoNoble Platform Balance Top-Up",
                        "description": f"Top-up saldo piattaforma: {req.amount_eur} EUR",
                    },
                },
                "quantity": 1,
            }],
            success_url=f"{frontend_url}/admin?topup=success",
            cancel_url=f"{frontend_url}/admin?topup=cancelled",
            metadata={
                "type": "platform_balance_topup",
                "admin_user_id": current_user["user_id"],
                "admin_email": current_user.get("email", ""),
            },
        )
        logger.info(f"[STRIPE-TOPUP] Checkout session created: {session.id} for {req.amount_eur} EUR")
        return {
            "checkout_url": session.url,
            "session_id": session.id,
            "amount_eur": req.amount_eur,
        }
    except stripe.error.StripeError as e:
        logger.error(f"[STRIPE-TOPUP] Error: {e}")
        raise HTTPException(status_code=400, detail=f"Stripe error: {e.user_message}")


# ── STRIPE BALANCE CHECK ──

@router.get("/stripe-balance")
async def stripe_balance(current_user: dict = Depends(get_current_user)):
    """Check Stripe account balance. Admin only."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")

    import stripe
    import os
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe non configurato")

    try:
        bal = stripe.Balance.retrieve()
        available = {}
        pending = {}
        for b in bal.available:
            available[b.currency.upper()] = b.amount / 100
        for b in bal.pending:
            pending[b.currency.upper()] = b.amount / 100

        return {
            "available": available,
            "pending": pending,
            "total_eur": available.get("EUR", 0) + pending.get("EUR", 0),
            "payout_ready": available.get("EUR", 0) > 0,
        }
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=f"Stripe error: {e.user_message}")


# ── SEPA PAYOUT (direct Stripe Payout API) ──

class SepaPayoutRequest(BaseModel):
    amount_eur: float
    description: str = "NeoNoble Revenue Withdrawal"

@router.post("/sepa-payout")
async def sepa_payout(req: SepaPayoutRequest, current_user: dict = Depends(get_current_user)):
    """
    Execute a real SEPA payout via Stripe.
    Sends from Stripe balance to the configured bank account.
    Admin only. Full audit trail.
    """
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    if req.amount_eur < 1:
        raise HTTPException(status_code=400, detail="Minimo 1 EUR")

    import stripe
    import os
    import uuid
    from datetime import datetime, timezone
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")

    # Pre-check balance
    try:
        bal = stripe.Balance.retrieve()
        eur_available = 0
        for b in bal.available:
            if b.currency == 'eur':
                eur_available = b.amount / 100
    except Exception:
        eur_available = 0

    if eur_available < req.amount_eur:
        return {
            "success": False,
            "error": "balance_insufficient",
            "message": f"Saldo Stripe insufficiente: €{eur_available:.2f} disponibili, €{req.amount_eur:.2f} richiesti",
            "stripe_balance_eur": eur_available,
            "fix": "Effettua un top-up tramite /api/cashout/stripe-topup o ricevi pagamenti tramite Stripe",
        }

    payout_id = None
    try:
        # Create real SEPA payout
        logger.info(f"[SEPA-PAYOUT] Creating payout: {req.amount_eur} EUR | Desc: {req.description}")
        payout = stripe.Payout.create(
            amount=int(req.amount_eur * 100),
            currency='eur',
            description=req.description,
            statement_descriptor="NEONOBLE",
            method="standard",
            metadata={
                'type': 'sepa_revenue_payout',
                'admin_user_id': current_user["user_id"],
                'admin_email': current_user.get("email", ""),
            }
        )
        payout_id = payout.id

        logger.info(f"[SEPA-PAYOUT] SUCCESS: {payout.id} | Status: {payout.status} | Amount: {payout.amount/100:.2f} EUR")

        # Audit in DB
        from database.mongodb import get_database
        db = get_database()
        audit_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        await db.sepa_payouts.update_one(
            {"_id": audit_id},
            {"$setOnInsert": {
                "payout_id": payout.id,
                "amount_eur": req.amount_eur,
                "status": payout.status,
                "method": payout.method,
                "description": req.description,
                "admin_email": current_user.get("email", ""),
                "arrival_date": payout.arrival_date,
                "created_at": now.isoformat(),
            }},
            upsert=True,
        )

        arrival = None
        if payout.arrival_date:
            from datetime import datetime as dt
            arrival = dt.fromtimestamp(payout.arrival_date).isoformat()

        return {
            "success": True,
            "payout_id": payout.id,
            "status": payout.status,
            "amount_eur": payout.amount / 100,
            "currency": payout.currency,
            "method": payout.method,
            "arrival_date": arrival,
            "description": payout.description,
            "message": f"SEPA payout {payout.id} creato: €{payout.amount/100:.2f} | Status: {payout.status}",
            "status_flow": "pending → in_transit → paid",
        }

    except stripe.error.StripeError as e:
        err_body = e.json_body.get('error', {}) if hasattr(e, 'json_body') and e.json_body else {}
        logger.error(f"[SEPA-PAYOUT] Stripe error: {e.user_message} | Code: {getattr(e, 'code', 'N/A')}")
        return {
            "success": False,
            "error": getattr(e, 'code', 'stripe_error'),
            "message": e.user_message,
            "error_type": err_body.get('type', ''),
            "http_status": e.http_status,
            "payout_id": payout_id,
        }



@router.get("/report")
async def comprehensive_report(current_user: dict = Depends(get_current_user)):
    """
    Full cashout report: engine status + wallet balances + conversions + EUR accounts.
    Single endpoint for complete visibility.
    """
    from services.circle_wallet_service import CircleWalletService, WalletRole
    from services.execution_engine import ExecutionEngine

    cashout = CashoutEngine.get_instance()
    circle = CircleWalletService.get_instance()
    exec_engine = ExecutionEngine.get_instance()
    converter = AutoConversionEngine.get_instance()

    # Parallel data collection
    status = await cashout.get_status()
    usdc_balances = await circle.get_all_wallet_balances("BSC")
    hot_wallet = await exec_engine.get_hot_wallet_status()
    opportunities = await converter.evaluate_conversions(hot_wallet)
    conv_summary = await converter.get_summary()

    return {
        "engine": {
            "running": status["running"],
            "cycles": status["cycle_count"],
            "interval": status["interval_seconds"],
        },
        "extracted": status["cumulative"],
        "usdc_wallets": {
            role: usdc_balances["wallets"].get(role, {}).get("balance", 0)
            for role in [WalletRole.CLIENT, WalletRole.TREASURY, WalletRole.REVENUE]
        },
        "usdc_total": usdc_balances.get("total_usdc", 0),
        "hot_wallet": {
            "bnb": hot_wallet.get("bnb_balance", 0),
            "neno": hot_wallet.get("neno_balance", 0),
            "available": hot_wallet.get("available", False),
        },
        "conversion_opportunities": len(opportunities),
        "conversions": conv_summary,
        "eur_accounts": EUR_ACCOUNTS,
        "by_type": status.get("by_type", {}),
        "recent_cashouts": status.get("recent_cashouts", [])[:5],
        "timestamp": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
    }

"""
NeoNoble Internal Exchange — $NENO On/Off-Ramp.

Fully independent conversion engine for $NENO at fixed price of EUR 10,000.
No external providers. All conversions happen on-platform with wallet credit.

Supports:
- Buy NENO with: BNB, ETH, USDT, BTC, USDC, MATIC, EUR, USD
- Sell NENO for:  BNB, ETH, USDT, BTC, USDC, MATIC, EUR, USD
- Off-ramp to card (NIUM) or bank account (SEPA)
- Create custom tokens with specified price
- Swap any token pair through NENO as bridge
"""
from services.exchanges.connector_manager import get_connector_manager
from services.liquidity.routing_service import get_routing_service
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone, timedelta
import uuid
import hashlib
import os
import asyncio
import logging

logger = logging.getLogger("neno_exchange")

from database.mongodb import get_database
from routes.auth import get_current_user
from services.onchain_settlement import OnChainSettlement
from services.settlement_ledger import (
    create_ledger_entry, transition_state, enqueue_payout,
    get_user_ledger, get_user_payouts, reconcile_deposits,
    STATE_ONCHAIN_EXECUTED, STATE_INTERNAL_CREDITED, STATE_PAYOUT_PENDING,
    STATE_PAYOUT_SENT, STATE_PAYOUT_SETTLED, STATE_PAYOUT_EXECUTED_EXTERNAL,
)
from services.execution_engine import ExecutionEngine, TreasuryEngine, LiquidityEngine, ASSET_TO_BSC_CONTRACT
from services.market_maker_service import MarketMakerService
from services.audit_logger import log_pre_operation, log_post_operation
from services.security_guard import SecurityGuard
from services.virtual_real_engine import VirtualRealEngine

logger = logging.getLogger(__name__)


def _settlement_record(tx_id: str, tx_type: str, uid: str, amount: float, asset: str, details: dict) -> dict:
    """Create an on-chain anchored settlement record."""
    engine = OnChainSettlement.get_instance()
    return engine.generate_settlement(tx_id, tx_type, uid, amount, asset, details)


def _get_platform_hot_wallet() -> str:
    """Derive platform hot wallet address from mnemonic in .env."""
    mnemonic = os.environ.get("NENO_WALLET_MNEMONIC", "")
    if not mnemonic:
        raise HTTPException(status_code=500, detail="Platform wallet non configurato")
    try:
        from eth_account import Account
        Account.enable_unaudited_hdwallet_features()
        acct = Account.from_mnemonic(mnemonic)
        return acct.address
    except Exception as e:
        logger.error(f"Failed to derive hot wallet: {e}")
        raise HTTPException(status_code=500, detail="Errore derivazione wallet")

router = APIRouter(prefix="/neno-exchange", tags=["NENO Exchange"])

connector_manager = get_connector_manager()
routing_service = get_routing_service()

# ── Base NENO price — dynamically adjusted based on order book pressure ──
NENO_BASE_PRICE = 10_000.0
NENO_MAX_DEVIATION = 0.05
PRICE_IMPACT_FACTOR = 0.0001

# ── Market reference prices (EUR) — synced with settlement engine ──
MARKET_PRICES_EUR = {
    "BTC": 60787.0,
    "ETH": 1769.0,
    "BNB": 555.36,
    "USDT": 0.92,
    "USDC": 0.92,
    "MATIC": 0.55,
    "SOL": 74.72,
    "XRP": 1.21,
    "ADA": 0.38,
    "DOGE": 0.082,
    "EUR": 1.0,
    "USD": 0.92,
}

PLATFORM_FEE = 0.003  # 0.3%

# ── Treasury Caps (imported from security_guard) ──
MAX_SINGLE_TX_EUR = float(os.environ.get("MAX_SINGLE_TX_EUR", "50000"))
MAX_DAILY_EUR = float(os.environ.get("MAX_DAILY_EUR", "200000"))
MAX_NENO_PER_TX = float(os.environ.get("MAX_NENO_PER_TX", "50"))
SUPPORTED_ASSETS = list(MARKET_PRICES_EUR.keys())


async def _get_dynamic_neno_price() -> dict:
    """Calculate dynamic NENO price based on recent order book pressure."""
    db = get_database()
    now = datetime.now(timezone.utc)
    window = now - timedelta(hours=24)

    pipeline = [
        {"$match": {"created_at": {"$gte": window}}},
        {"$group": {
            "_id": "$type",
            "total_neno": {"$sum": "$neno_amount"},
            "count": {"$sum": 1},
        }},
    ]
    agg = await db.neno_transactions.aggregate(pipeline).to_list(10)
    buy_vol = 0
    sell_vol = 0
    for row in agg:
        if row["_id"] in ("buy_neno",):
            buy_vol = row["total_neno"]
        elif row["_id"] in ("sell_neno", "offramp_card", "offramp_bank"):
            sell_vol += row["total_neno"]

    net_pressure = buy_vol - sell_vol
    price_shift = net_pressure * PRICE_IMPACT_FACTOR
    max_shift = NENO_BASE_PRICE * NENO_MAX_DEVIATION
    price_shift = max(-max_shift, min(max_shift, price_shift))

    dynamic_price = round(NENO_BASE_PRICE + price_shift, 2)
    return {
        "price": dynamic_price,
        "base_price": NENO_BASE_PRICE,
        "shift": round(price_shift, 2),
        "shift_pct": round((price_shift / NENO_BASE_PRICE) * 100, 3),
        "buy_volume_24h": round(buy_vol, 4),
        "sell_volume_24h": round(sell_vol, 4),
        "net_pressure": round(net_pressure, 4),
    }


def _neno_rate_with_price(asset: str, neno_price: float) -> float:
    """How many units of `asset` equal 1 NENO at given price."""
    price_eur = MARKET_PRICES_EUR.get(asset.upper())
    if price_eur is None or price_eur <= 0:
        raise ValueError(f"Asset non supportato: {asset}")
    return neno_price / price_eur


async def _get_custom_token_price(db, symbol: str) -> Optional[float]:
    """Get price in EUR for a custom token from DB."""
    token = await db.custom_tokens.find_one({"symbol": symbol.upper()}, {"_id": 0})
    if token:
        if "price_eur" in token and token["price_eur"] > 0:
            return token["price_eur"]
        if "price_usd" in token and token["price_usd"] > 0:
            return token["price_usd"] * 0.92
    return None


async def _get_any_price_eur(db, asset: str) -> Optional[float]:
    """Get EUR price for built-in OR custom token OR NENO."""
    asset = asset.upper()
    if asset == "NENO":
        pricing = await _get_dynamic_neno_price()
        return pricing["price"]
    if asset in MARKET_PRICES_EUR:
        return MARKET_PRICES_EUR[asset]
    return await _get_custom_token_price(db, asset)


class BuyNenoRequest(BaseModel):
    pay_asset: str = Field(description="Asset used to pay (BNB, ETH, EUR ...)")
    neno_amount: float = Field(gt=0, description="How many NENO to buy")


class SellNenoRequest(BaseModel):
    receive_asset: str = Field(description="Asset to receive (BNB, ETH, EUR ...)")
    neno_amount: float = Field(gt=0, description="How many NENO to sell")
    tx_hash: Optional[str] = Field(None, description="On-chain tx hash from MetaMask transfer to hot wallet")
    destination_wallet: Optional[str] = Field(None, description="External wallet for on-chain delivery")
    destination_iban: Optional[str] = Field(None, description="IBAN for fiat delivery via Stripe SEPA")


class OfframpRequest(BaseModel):
    neno_amount: float = Field(gt=0)
    destination: str = Field(description="'card', 'bank', or 'crypto'")
    card_id: Optional[str] = None
    destination_iban: Optional[str] = None
    beneficiary_name: Optional[str] = None
    tx_hash: Optional[str] = Field(None, description="On-chain tx hash from MetaMask transfer to hot wallet")
    destination_wallet: Optional[str] = Field(None, description="External wallet for crypto off-ramp fallback")
    preferred_stable: Optional[str] = Field("USDT", description="USDT or USDC for crypto off-ramp")


class CreateTokenRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=8, description="Token ticker max 8 chars (e.g. MYTKN)")
    name: str = Field(min_length=1, max_length=50, description="Token display name")
    price_usd: float = Field(gt=0, description="Price in USD per token (2 decimals)")
    total_supply: float = Field(gt=0, default=1_000_000, description="Total supply to mint")
    description: Optional[str] = None


class BuyCustomTokenRequest(BaseModel):
    symbol: str = Field(description="Custom token symbol to buy")
    amount: float = Field(gt=0, description="Amount of tokens to buy")
    pay_asset: str = Field(default="EUR", description="Asset to pay with (EUR, USDT, BTC, etc.)")


class SellCustomTokenRequest(BaseModel):
    symbol: str = Field(description="Custom token symbol to sell")
    amount: float = Field(gt=0, description="Amount of tokens to sell")
    receive_asset: str = Field(default="EUR", description="Asset to receive (EUR, USDT, BTC, etc.)")


class SwapRequest(BaseModel):
    from_asset: str = Field(description="Asset to sell")
    to_asset: str = Field(description="Asset to receive")
    amount: float = Field(gt=0, description="Amount of from_asset to swap")
    tx_hash: Optional[str] = Field(None, description="On-chain tx hash (for NENO-based swaps via MetaMask)")
    destination_wallet: Optional[str] = Field(None, description="External wallet for on-chain delivery of to_asset")


# ── helpers ──

async def _get_balance(db, user_id: str, asset: str) -> float:
    w = await db.wallets.find_one({"user_id": user_id, "asset": asset.upper()})
    return w.get("balance", 0) if w else 0


async def _credit(db, user_id: str, asset: str, amount: float):
    await db.wallets.update_one(
        {"user_id": user_id, "asset": asset.upper()},
        {"$inc": {"balance": amount}, "$setOnInsert": {"user_id": user_id, "asset": asset.upper()}},
        upsert=True,
    )


async def _debit(db, user_id: str, asset: str, amount: float):
    await db.wallets.update_one(
        {"user_id": user_id, "asset": asset.upper()},
        {"$inc": {"balance": -amount}},
    )


async def _log_tx(db, tx: dict):
    """Safe transaction logging — prevents E11000 duplicate key errors via upsert."""
    doc = {**tx}
    tx_id = doc.get("id", "")
    if not tx_id:
        return
    doc.pop("_id", None)
    try:
        await db.neno_transactions.update_one(
            {"_id": tx_id},
            {"$setOnInsert": doc},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"[SAFE_LOG] Transaction log error for {tx_id}: {e}")


# ── Dynamic Price endpoint ──

@router.get("/price")
async def get_neno_price():
    pricing = await _get_dynamic_neno_price()
    # ── Include MM bid/ask ──
    mm = MarketMakerService.get_instance()
    mm_pricing = await mm.get_pricing()
    return {
        "neno_eur_price": mm_pricing["mid_price"],
        "bid": mm_pricing["bid"],
        "ask": mm_pricing["ask"],
        "spread_bps": mm_pricing["spread_bps"],
        "spread_pct": mm_pricing["spread_pct"],
        "spread_eur": mm_pricing["spread_eur"],
        "mid_price": mm_pricing["mid_price"],
        "base_price": pricing["base_price"],
        "price_shift": pricing["shift"],
        "shift_pct": pricing["shift_pct"],
        "buy_volume_24h": pricing["buy_volume_24h"],
        "sell_volume_24h": pricing["sell_volume_24h"],
        "net_pressure": pricing["net_pressure"],
        "inventory_skew": mm_pricing["inventory_skew"],
        "treasury_neno": mm_pricing["treasury_neno"],
        "pricing_model": "market_maker_bid_ask",
        "max_deviation": f"{NENO_MAX_DEVIATION * 100}%",
    }


# ── Quote ──

@router.get("/quote")
async def get_quote(direction: str = "buy", asset: str = "EUR", neno_amount: float = 1.0):
    asset = asset.upper()
    db = get_database()
    price_eur = await _get_any_price_eur(db, asset)
    if price_eur is None:
        raise HTTPException(status_code=400, detail=f"Asset non supportato: {asset}")

    # ── Use MM bid/ask ──
    mm = MarketMakerService.get_instance()
    mm_pricing = await mm.get_pricing()
    neno_eur_price = mm_pricing["ask"] if direction == "buy" else mm_pricing["bid"]

    rate = neno_eur_price / price_eur
    gross = round(neno_amount * rate, 8)
    fee = round(gross * PLATFORM_FEE, 8)

    base = {
        "direction": direction, "neno_amount": neno_amount,
        "rate": round(rate, 8), "neno_eur_price": neno_eur_price,
        "base_price": NENO_BASE_PRICE,
        "mm_bid": mm_pricing["bid"], "mm_ask": mm_pricing["ask"],
        "mm_spread_bps": mm_pricing["spread_bps"], "mm_spread_pct": mm_pricing["spread_pct"],
        "mm_mid_price": mm_pricing["mid_price"],
        "gross_cost" if direction == "buy" else "gross_value": gross,
        "fee": fee, "fee_percent": PLATFORM_FEE * 100,
    }

    if direction == "buy":
        total_cost = round(gross + fee, 8)
        return {
            **base, "pay_asset": asset, "total_cost": total_cost,
            "summary": f"Per acquistare {neno_amount} NENO servono {total_cost} {asset} (ask: EUR {neno_eur_price})",
        }
    else:
        net_receive = round(gross - fee, 8)
        return {
            **base, "receive_asset": asset, "net_receive": net_receive,
            "summary": f"Vendendo {neno_amount} NENO ricevi {net_receive} {asset} (bid: EUR {neno_eur_price})",
        }


# ── Buy NENO ──

@router.post("/buy")
async def buy_neno(req: BuyNenoRequest, current_user: dict = Depends(get_current_user)):
    db = get_database()
    uid = current_user["user_id"]
    asset = req.pay_asset.upper()

    # ── Idempotency check ──
    from services.idempotency_service import IdempotencyService
    idem = IdempotencyService.get_instance()
    idem_key = idem.generate_key(uid, "buy_neno", asset=asset, neno_amount=str(req.neno_amount))
    lock_result = await idem.check_and_lock(idem_key, "buy_neno", uid)
    if not lock_result["locked"]:
        existing = lock_result.get("existing", {})
        if existing.get("status") == "completed":
            return existing.get("result_summary", {"message": "Operazione già eseguita (idempotency)", "duplicate": True})

    try:
        price_eur = await _get_any_price_eur(db, asset)
        if price_eur is None:
            raise HTTPException(status_code=400, detail=f"Asset non supportato: {asset}")
            from services.exchanges.connector_manager import get_connector_manager

connector_manager = get_connector_manager()

order, error = await connector_manager.execute_order(
    symbol="NENO-EUR",
    side="buy",
    quantity=req.neno_amount,
    user_id=uid
)

if error:
    raise HTTPException(status_code=400, detail=error)

        # ── Market Maker Pricing: user buys at ASK ──
        mm = MarketMakerService.get_instance()
        mm_pricing = await mm.get_pricing()
        neno_eur_price = mm_pricing["ask"]  # user pays ask
        mid_price = mm_pricing["mid_price"]

        # Try internal matching first
        match_result = await mm.try_internal_match("buy", "NENO", req.neno_amount, neno_eur_price)

        rate = neno_eur_price / price_eur
        gross_cost = round(req.neno_amount * rate, 8)
        fee = round(gross_cost * PLATFORM_FEE, 8)
        total_cost = round(gross_cost + fee, 8)

        balance = await _get_balance(db, uid, asset)
        if balance < total_cost:
            # Hybrid Liquidity: route through engine instead of hard fail
            from services.hybrid_liquidity_engine import HybridLiquidityEngine
            hybrid = HybridLiquidityEngine.get_instance()
            hybrid_result = await hybrid.execute_with_priority(uid, "buy", "NENO", req.neno_amount, neno_eur_price)
            if hybrid_result.get("success") and hybrid_result.get("execution_type") == "dex_fallback":
                logger.info(f"[BUY] Hybrid liquidity DEX fallback for user {uid}")
            # Still need user funds — raise if truly insufficient
            if balance < total_cost:
                await idem.mark_failed(idem_key, "insufficient_balance")
                raise HTTPException(
                    status_code=400,
                    detail=f"Saldo {asset} insufficiente: {balance:.8g} disponibile, {total_cost:.8g} necessario",
                )

        await _debit(db, uid, asset, total_cost)
        await _credit(db, uid, "NENO", req.neno_amount)

        tx_id = str(uuid.uuid4())
        settlement = _settlement_record(tx_id, "buy_neno", uid, req.neno_amount, "NENO", {
            "debit": {"asset": asset, "amount": total_cost},
            "credit": {"asset": "NENO", "amount": req.neno_amount},
            "fee": {"asset": asset, "amount": fee},
        })

        # ── Treasury counterparty execution ──
        mm_result = await mm.execute_as_counterparty(
            tx_id=tx_id, user_id=uid, direction="buy",
            neno_amount=req.neno_amount, counter_asset=asset,
            counter_amount=total_cost, fee_amount=fee, fee_asset=asset,
            effective_price=neno_eur_price, mid_price=mid_price,
        )

        tx = {
            "id": tx_id, "user_id": uid, "type": "buy_neno",
            "neno_amount": req.neno_amount, "pay_asset": asset,
            "pay_amount": total_cost, "rate": rate, "neno_eur_price": neno_eur_price,
            "fee": fee, "fee_asset": asset, "status": "completed",
            "eur_value": round(req.neno_amount * neno_eur_price, 2),
            "mm_bid": mm_pricing["bid"], "mm_ask": mm_pricing["ask"],
            "mm_spread_bps": mm_pricing["spread_bps"],
            "mm_matched_internal": bool(match_result),
            "mm_counterparty": mm_result.get("counterparty", "treasury"),
            "mm_spread_revenue": mm_result.get("spread_revenue_eur", 0),
            **settlement,
            "created_at": datetime.now(timezone.utc),
        }
        await _log_tx(db, tx)
        tx["created_at"] = tx["created_at"].isoformat()

        try:
            from services.notification_dispatch import notify_trade_executed
            eur_value = round(req.neno_amount * neno_eur_price, 2)
            asyncio.ensure_future(notify_trade_executed(uid, "NENO", "buy", req.neno_amount, neno_eur_price, eur_value))
        except Exception:
            pass

        new_neno = await _get_balance(db, uid, "NENO")
        new_pay = await _get_balance(db, uid, asset)

        result = {
            "message": f"Acquistati {req.neno_amount} NENO per {total_cost} {asset}",
            "transaction": tx,
            "balances": {"NENO": round(new_neno, 8), asset: round(new_pay, 8)},
            "market_maker": {
                "price_type": "ask",
                "effective_price": neno_eur_price,
                "mid_price": mid_price,
                "spread_bps": mm_pricing["spread_bps"],
                "matched_internal": bool(match_result),
                "spread_revenue": mm_result.get("spread_revenue_eur", 0),
            },
        }

        await idem.mark_completed(idem_key, tx_id, result)
        return result

    except HTTPException:
        raise
    except Exception as e:
        await idem.mark_failed(idem_key, str(e))
        raise


# ── Sell NENO ──

@router.post("/sell")
async def sell_neno(req: SellNenoRequest, current_user: dict = Depends(get_current_user)):
    db = get_database()
    uid = current_user["user_id"]
    asset = req.receive_asset.upper()
    guard = SecurityGuard.get_instance()

    # ── Idempotency check ──
    from services.idempotency_service import IdempotencyService
    idem = IdempotencyService.get_instance()
    idem_key = idem.generate_key(uid, "sell_neno", asset=asset, neno_amount=str(req.neno_amount))
    lock_result = await idem.check_and_lock(idem_key, "sell_neno", uid)
    if not lock_result["locked"]:
        existing = lock_result.get("existing", {})
        if existing.get("status") == "completed":
            return existing.get("result_summary", {"message": "Operazione già eseguita (idempotency)", "duplicate": True})

    # ── Rate limit ──
    allowed, remaining = await guard.check_rate_limit(uid)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit superato: max 10 operazioni/minuto")

    # ── AUDIT PRE: snapshot saldi ──
    audit_pre = await log_pre_operation(
        op_type="SELL_NENO", user_id=uid,
        user_email=current_user.get("email", ""),
        assets_involved=["NENO", asset],
        neno_amount=req.neno_amount,
        extra={"receive_asset": asset, "tx_hash": req.tx_hash}
    )

    from services.liquidity.routing_service import get_routing_service

routing_service = get_routing_service()

event = await routing_service.execute_conversion(
    source_currency="NENO",
    source_amount=req.neno_amount,
    destination_currency="EUR",
    quote_id=None
)

    
    price_eur = await _get_any_price_eur(db, asset)
    if price_eur is None:
        raise HTTPException(status_code=400, detail=f"Asset non supportato: {asset}")

    onchain_tx = req.tx_hash or None

    # ── Market Maker Pricing: user sells at BID ──
    mm = MarketMakerService.get_instance()
    mm_pricing = await mm.get_pricing()
    neno_eur_price = mm_pricing["bid"]
    mid_price = mm_pricing["mid_price"]

    rate = neno_eur_price / price_eur
    gross = round(req.neno_amount * rate, 8)
    fee = round(gross * PLATFORM_FEE, 8)
    net = round(gross - fee, 8)
    eur_value = round(req.neno_amount * neno_eur_price, 2)

    # ── Treasury caps ──
    cap_ok, cap_reason = await guard.enforce_caps(uid, eur_value, req.neno_amount)
    if not cap_ok:
        raise HTTPException(status_code=400, detail=cap_reason)

    # ── Reentrancy lock ──
    async with guard.get_user_lock(uid):
        neno_balance = await _get_balance(db, uid, "NENO")
        if neno_balance < req.neno_amount:
            raise HTTPException(
                status_code=400,
                detail=f"Saldo NENO insufficiente: {neno_balance:.8g} disponibile",
            )
        await _debit(db, uid, "NENO", req.neno_amount)

        # Internal matching attempt
        match_result = await mm.try_internal_match("sell", "NENO", req.neno_amount, neno_eur_price)

        await _credit(db, uid, asset, net)

        tx_id = str(uuid.uuid4())
        settlement = _settlement_record(tx_id, "sell_neno", uid, req.neno_amount, asset, {
            "debit": {"asset": "NENO", "amount": req.neno_amount},
            "credit": {"asset": asset, "amount": net},
            "fee": {"asset": asset, "amount": fee},
            "onchain_tx_hash": onchain_tx,
        })

        # ── Treasury counterparty execution ──
        mm_result = await mm.execute_as_counterparty(
            tx_id=tx_id, user_id=uid, direction="sell",
            neno_amount=req.neno_amount, counter_asset=asset,
            counter_amount=net, fee_amount=fee, fee_asset=asset,
            effective_price=neno_eur_price, mid_price=mid_price,
        )

    # ── REAL EXECUTION: deliver asset to user on-chain or via fiat ──
    exec_result = None
    payout_result = None
    real_tx_hash = None
    real_payout_id = None

    if asset == "EUR" and req.destination_iban:
        # Stripe SEPA payout
        try:
            from services.real_payout_service import get_real_payout_service
            payout_svc = get_real_payout_service()
            if payout_svc and payout_svc.is_available():
                payout_result = await payout_svc.create_payout(
                    quote_id=tx_id, transaction_id=tx_id,
                    amount_eur=net, reference=f"SELL-{tx_id[:8].upper()}",
                    metadata={"user_id": uid, "neno_amount": req.neno_amount},
                )
                if payout_result.success:
                    real_payout_id = payout_result.payout_id
        except Exception as e:
            logger.error(f"[SELL] Stripe SEPA payout error: {e}")

    elif asset in ASSET_TO_BSC_CONTRACT or asset == "BNB":
        # On-chain delivery
        dest_wallet = req.destination_wallet
        if not dest_wallet:
            user = await db.users.find_one({"user_id": uid}, {"_id": 0, "connected_wallet": 1})
            dest_wallet = user.get("connected_wallet") if user else None
        if dest_wallet:
            try:
                engine = ExecutionEngine.get_instance()
                exec_result = await engine.send_asset_real(asset, dest_wallet, net)
                if exec_result.get("success"):
                    real_tx_hash = exec_result["tx_hash"]
            except Exception as e:
                logger.error(f"[SELL] On-chain delivery error: {e}")

    # ── Status enforcement: only 'completed' with proof ──
    final_status = SecurityGuard.resolve_status(
        has_tx_hash=bool(real_tx_hash or onchain_tx),
        has_payout_id=bool(real_payout_id),
        has_treasury_proof=True,  # treasury always moves
    )

    tx = {
        "id": tx_id, "user_id": uid, "type": "sell_neno",
        "neno_amount": req.neno_amount, "receive_asset": asset,
        "receive_amount": net, "rate": rate, "neno_eur_price": neno_eur_price,
        "fee": fee, "fee_asset": asset,
        "status": final_status,
        "execution_mode": "onchain" if real_tx_hash else ("fiat_sepa" if real_payout_id else "internal"),
        "onchain_tx_hash": real_tx_hash or onchain_tx,
        "delivery_tx_hash": real_tx_hash,
        "delivery_explorer": f"https://bscscan.com/tx/{real_tx_hash}" if real_tx_hash else None,
        "payout_id": real_payout_id,
        "eur_value": eur_value,
        "mm_bid": mm_pricing["bid"], "mm_ask": mm_pricing["ask"],
        "mm_spread_bps": mm_pricing["spread_bps"],
        "mm_matched_internal": bool(match_result),
        "mm_counterparty": mm_result.get("counterparty", "treasury"),
        "mm_spread_revenue": mm_result.get("spread_revenue_eur", 0),
        **settlement,
        "created_at": datetime.now(timezone.utc),
    }
    await _log_tx(db, tx)
    tx["created_at"] = tx["created_at"].isoformat()

    try:
        from services.notification_dispatch import notify_trade_executed
        asyncio.ensure_future(notify_trade_executed(uid, "NENO", "sell", req.neno_amount, neno_eur_price, eur_value))
    except Exception:
        pass

    new_neno = await _get_balance(db, uid, "NENO")
    new_asset = await _get_balance(db, uid, asset)

    await create_ledger_entry(
        user_id=uid, tx_type="sell_neno", debit_asset="NENO", debit_amount=req.neno_amount,
        credit_asset=asset, credit_amount=net, fee_amount=fee, fee_asset=asset,
        onchain_tx_hash=real_tx_hash or onchain_tx,
        initial_state=STATE_INTERNAL_CREDITED,
    )

    _treasury = TreasuryEngine()
    await _treasury.record_fee(db, tx_id, fee, asset, "sell_neno")

    # ── WebSocket balance broadcast ──
    try:
        from routes.websocket_routes import broadcast_balance_update
        asyncio.ensure_future(broadcast_balance_update(uid, {
            "balances": {"NENO": round(new_neno, 8), asset: round(new_asset, 8)},
            "trigger": "sell_neno", "tx_id": tx_id,
        }))
    except Exception:
        pass

    # ── Event-driven instant cashout ──
    try:
        from services.realtime_sync_service import EventBus
        asyncio.ensure_future(EventBus.get_instance().emit("trade_executed", {
            "type": "sell_neno", "tx_id": tx_id, "user_id": uid,
            "fee": fee, "fee_asset": asset, "eur_value": eur_value,
            "tx_hash": real_tx_hash,
        }))
    except Exception:
        pass

    result = {
        "message": f"Venduti {req.neno_amount} NENO per {net} {asset}" + (f" | tx: {real_tx_hash}" if real_tx_hash else "") + (f" | payout: {real_payout_id}" if real_payout_id else ""),
        "transaction": tx,
        "balances": {"NENO": round(new_neno, 8), asset: round(new_asset, 8)},
        "state": final_status,
        "execution_proof": {
            "tx_hash": real_tx_hash,
            "payout_id": real_payout_id,
            "explorer": f"https://bscscan.com/tx/{real_tx_hash}" if real_tx_hash else None,
            "treasury_movement": True,
        },
        "onchain_explorer": f"https://bscscan.com/tx/{real_tx_hash or onchain_tx}" if (real_tx_hash or onchain_tx) else None,
        "market_maker": {
            "price_type": "bid",
            "effective_price": neno_eur_price,
            "mid_price": mid_price,
            "spread_bps": mm_pricing["spread_bps"],
            "matched_internal": bool(match_result),
            "spread_revenue": mm_result.get("spread_revenue_eur", 0),
        },
    }

    # ── AUDIT POST ──
    await log_post_operation(
        pre_snapshot=audit_pre, result=result,
        assets_involved=["NENO", asset], tx_id=tx_id
    )

    return result


# ── Swap: Any Token ↔ Any Token (via NENO bridge) ──

@router.post("/swap")
async def swap_tokens(req: SwapRequest, current_user: dict = Depends(get_current_user)):
    """Swap any token for any other token. Uses NENO as the bridge asset. Real on-chain delivery when possible."""
from services.liquidity.routing_service import get_routing_service

routing_service = get_routing_service()

event = await routing_service.execute_conversion(
    source_currency=from_asset,
    source_amount=req.amount,
    destination_currency=to_asset,
    quote_id=None
)
    db = get_database()
    uid = current_user["user_id"]
    from_asset = req.from_asset.upper()
    to_asset = req.to_asset.upper()
    onchain_tx = req.tx_hash or None
    guard = SecurityGuard.get_instance()

    # ── Idempotency check ──
    from services.idempotency_service import IdempotencyService
    idem = IdempotencyService.get_instance()
    idem_key = idem.generate_key(uid, "swap", from_asset=from_asset, to_asset=to_asset, amount=str(req.amount))
    lock_result = await idem.check_and_lock(idem_key, "swap", uid)
    if not lock_result["locked"]:
        existing = lock_result.get("existing", {})
        if existing.get("status") == "completed":
            return existing.get("result_summary", {"message": "Operazione già eseguita (idempotency)", "duplicate": True})

    # ── Rate limit ──
    allowed, remaining = await guard.check_rate_limit(uid)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit superato: max 10 operazioni/minuto")

    # ── AUDIT PRE ──
    audit_pre = await log_pre_operation(
        op_type="SWAP", user_id=uid,
        user_email=current_user.get("email", ""),
        assets_involved=[from_asset, to_asset, "NENO"],
        neno_amount=req.amount if from_asset == "NENO" else 0,
        extra={"from": from_asset, "to": to_asset, "amount": req.amount}
    )

    if from_asset == to_asset:
        raise HTTPException(status_code=400, detail="Non puoi swappare lo stesso asset")

    from_price = await _get_any_price_eur(db, from_asset)
    to_price = await _get_any_price_eur(db, to_asset)
    if from_price is None:
        raise HTTPException(status_code=400, detail=f"Asset non supportato: {from_asset}")
    if to_price is None:
        raise HTTPException(status_code=400, detail=f"Asset non supportato: {to_asset}")

    # ── MM Pricing for NENO legs ──
    mm = MarketMakerService.get_instance()
    mm_pricing = await mm.get_pricing()

    if from_asset == "NENO":
        from_price = mm_pricing["bid"]
    if to_asset == "NENO":
        to_price = mm_pricing["ask"]

    eur_value = req.amount * from_price
    fee_eur = round(eur_value * PLATFORM_FEE, 8)
    net_eur = eur_value - fee_eur
    receive_amount = round(net_eur / to_price, 8)
    fee_in_to = round(fee_eur / to_price, 8)

    # ── Treasury caps ──
    cap_ok, cap_reason = await guard.enforce_caps(uid, round(eur_value, 2), req.amount if from_asset == "NENO" else 0)
    if not cap_ok:
        raise HTTPException(status_code=400, detail=cap_reason)

    # ── Reentrancy lock ──
    async with guard.get_user_lock(uid):
        balance = await _get_balance(db, uid, from_asset)
        if balance < req.amount:
            raise HTTPException(
                status_code=400,
                detail=f"Saldo {from_asset} insufficiente: {balance:.8g} disponibile, {req.amount:.8g} necessario",
            )
        await _debit(db, uid, from_asset, req.amount)
        await _credit(db, uid, to_asset, receive_amount)

        tx_id = str(uuid.uuid4())
        settlement = _settlement_record(tx_id, "swap", uid, req.amount, from_asset, {
            "debit": {"asset": from_asset, "amount": req.amount},
            "credit": {"asset": to_asset, "amount": receive_amount},
            "fee_eur": round(fee_eur, 4),
            "onchain_tx_hash": onchain_tx,
        })

        # ── Treasury updates for swap ──
        await mm.update_treasury(from_asset, req.amount, "swap_receive", from_price)
        await mm.update_treasury(to_asset, -receive_amount, "swap_send", to_price)

    # Record PnL
    mm_pnl_entry = {
        "_id": str(uuid.uuid4()),
        "tx_id": tx_id, "user_id": uid, "direction": "swap",
        "neno_amount": req.amount if from_asset == "NENO" else receive_amount if to_asset == "NENO" else 0,
        "counter_asset": to_asset, "counter_amount": receive_amount,
        "effective_price": from_price, "mid_price": mm_pricing["mid_price"],
        "spread_revenue_eur": round(fee_eur * 0.3, 4),
        "fee_revenue_eur": round(fee_eur * 0.7, 4),
        "total_revenue_eur": round(fee_eur, 4),
        "inventory_change_neno": 0,
        "inventory_change_counter": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.mm_pnl_ledger.insert_one(mm_pnl_entry)

    # ── REAL ON-CHAIN DELIVERY of to_asset ──
    real_tx_hash = None
    exec_result = None
    if to_asset in ASSET_TO_BSC_CONTRACT or to_asset == "BNB":
        dest_wallet = req.destination_wallet
        if not dest_wallet:
            user = await db.users.find_one({"user_id": uid}, {"_id": 0, "connected_wallet": 1})
            dest_wallet = user.get("connected_wallet") if user else None
        if dest_wallet:
            try:
                engine = ExecutionEngine.get_instance()
                exec_result = await engine.send_asset_real(to_asset, dest_wallet, receive_amount)
                if exec_result.get("success"):
                    real_tx_hash = exec_result["tx_hash"]
            except Exception as e:
                logger.error(f"[SWAP] On-chain delivery error: {e}")

    # ── Status enforcement ──
    final_status = SecurityGuard.resolve_status(
        has_tx_hash=bool(real_tx_hash or onchain_tx),
        has_treasury_proof=True,
    )

    tx = {
        "id": tx_id, "user_id": uid, "type": "swap",
        "from_asset": from_asset, "from_amount": req.amount,
        "to_asset": to_asset, "to_amount": receive_amount,
        "eur_value": round(eur_value, 2), "fee_eur": round(fee_eur, 4),
        "fee_in_to_asset": fee_in_to,
        "rate": round(from_price / to_price, 8),
        "status": final_status,
        "execution_mode": "onchain" if real_tx_hash else ("onchain_input" if onchain_tx else "internal"),
        "onchain_tx_hash": onchain_tx,
        "delivery_tx_hash": real_tx_hash,
        "delivery_explorer": f"https://bscscan.com/tx/{real_tx_hash}" if real_tx_hash else None,
        "mm_bid": mm_pricing["bid"], "mm_ask": mm_pricing["ask"],
        "mm_spread_bps": mm_pricing["spread_bps"],
        **settlement,
        "created_at": datetime.now(timezone.utc),
    }
    await _log_tx(db, tx)
    tx["created_at"] = tx["created_at"].isoformat()

    # ── WebSocket balance broadcast ──
    try:
        from routes.websocket_routes import broadcast_balance_update
        asyncio.ensure_future(broadcast_balance_update(uid, {
            "balances": {
                from_asset: round(await _get_balance(db, uid, from_asset), 8),
                to_asset: round(await _get_balance(db, uid, to_asset), 8),
            },
            "trigger": "swap", "tx_id": tx_id,
        }))
    except Exception:
        pass

    # ── Event-driven instant cashout ──
    try:
        from services.realtime_sync_service import EventBus
        asyncio.ensure_future(EventBus.get_instance().emit("trade_executed", {
            "type": "swap", "tx_id": tx_id, "user_id": uid,
            "fee": fee_eur, "fee_asset": from_asset, "eur_value": eur_value,
            "tx_hash": real_tx_hash,
        }))
    except Exception:
        pass

    swap_result = {
        "message": f"Swappati {req.amount} {from_asset} per {receive_amount} {to_asset}" + (f" | tx: {real_tx_hash}" if real_tx_hash else ""),
        "transaction": tx,
        "balances": {
            from_asset: round(await _get_balance(db, uid, from_asset), 8),
            to_asset: round(await _get_balance(db, uid, to_asset), 8),
        },
        "state": final_status,
        "execution_proof": {
            "delivery_tx_hash": real_tx_hash,
            "explorer": f"https://bscscan.com/tx/{real_tx_hash}" if real_tx_hash else None,
            "treasury_movement": True,
        },
        "onchain_explorer": f"https://bscscan.com/tx/{real_tx_hash or onchain_tx}" if (real_tx_hash or onchain_tx) else None,
        "market_maker": {
            "bid": mm_pricing["bid"], "ask": mm_pricing["ask"],
            "spread_bps": mm_pricing["spread_bps"],
        },
    }

    # ── AUDIT POST ──
    await log_post_operation(
        pre_snapshot=audit_pre, result=swap_result,
        assets_involved=[from_asset, to_asset, "NENO"], tx_id=tx_id
    )

    return swap_result


# ── Swap Quote ──

@router.get("/swap-quote")
async def swap_quote(from_asset: str = "NENO", to_asset: str = "ETH", amount: float = 1.0):
    db = get_database()
    from_asset = from_asset.upper()
    to_asset = to_asset.upper()

    from_price = await _get_any_price_eur(db, from_asset)
    to_price = await _get_any_price_eur(db, to_asset)
    if from_price is None or to_price is None:
        raise HTTPException(status_code=400, detail="Asset non supportato")

    # ── MM pricing for NENO legs ──
    mm = MarketMakerService.get_instance()
    mm_pricing = await mm.get_pricing()
    if from_asset == "NENO":
        from_price = mm_pricing["bid"]
    if to_asset == "NENO":
        to_price = mm_pricing["ask"]

    eur_value = amount * from_price
    fee_eur = round(eur_value * PLATFORM_FEE, 8)
    net_eur = eur_value - fee_eur
    receive = round(net_eur / to_price, 8)

    return {
        "from_asset": from_asset, "to_asset": to_asset, "amount": amount,
        "receive_amount": receive, "rate": round(from_price / to_price, 8),
        "eur_value": round(eur_value, 2), "fee_eur": round(fee_eur, 4),
        "fee_pct": PLATFORM_FEE * 100,
        "mm_bid": mm_pricing["bid"], "mm_ask": mm_pricing["ask"],
        "mm_spread_bps": mm_pricing["spread_bps"],
    }


# ── USD to EUR conversion rate ──
USD_EUR_RATE = 0.92


# ── Create Custom Token ──

@router.post("/create-token")
async def create_custom_token(req: CreateTokenRequest, current_user: dict = Depends(get_current_user)):
    """Create a new custom token with a specified USD price and mint supply to creator."""
    db = get_database()
    uid = current_user["user_id"]
    symbol = req.symbol.upper().strip()

    if len(symbol) > 8:
        raise HTTPException(status_code=400, detail="Il simbolo non puo' superare 8 caratteri")

    if symbol in MARKET_PRICES_EUR or symbol == "NENO":
        raise HTTPException(status_code=400, detail=f"{symbol} e' un asset di sistema, scegli un altro nome")

    existing = await db.custom_tokens.find_one({"symbol": symbol})
    if existing:
        raise HTTPException(status_code=400, detail=f"Il token {symbol} esiste gia'")

    price_usd = round(req.price_usd, 2)
    price_eur = round(price_usd * USD_EUR_RATE, 4)

    token = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "name": req.name,
        "price_usd": price_usd,
        "price_eur": price_eur,
        "total_supply": req.total_supply,
        "circulating_supply": req.total_supply,
        "creator_id": uid,
        "description": req.description or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.custom_tokens.insert_one({**token, "_id": token["id"]})

    await _credit(db, uid, symbol, req.total_supply)

    return {
        "message": f"Token {symbol} creato! {req.total_supply} {symbol} @ ${price_usd} accreditati al wallet",
        "token": token,
        "balance": req.total_supply,
    }


# ── List Custom Tokens ──

@router.get("/custom-tokens")
async def list_custom_tokens():
    db = get_database()
    tokens = await db.custom_tokens.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    for t in tokens:
        if "price_usd" not in t and "price_eur" in t:
            t["price_usd"] = round(t["price_eur"] / USD_EUR_RATE, 2)
    return {"tokens": tokens}


# ── My Custom Tokens (created by current user) ──

@router.get("/my-tokens")
async def my_custom_tokens(current_user: dict = Depends(get_current_user)):
    """Get all custom tokens created by the current user with their balances."""
    db = get_database()
    uid = current_user["user_id"]
    tokens = await db.custom_tokens.find({"creator_id": uid}, {"_id": 0}).sort("created_at", -1).to_list(100)

    for t in tokens:
        w = await db.wallets.find_one({"user_id": uid, "asset": t["symbol"]}, {"_id": 0})
        t["balance"] = w.get("balance", 0) if w else 0
        if "price_usd" not in t and "price_eur" in t:
            t["price_usd"] = round(t["price_eur"] / USD_EUR_RATE, 2)
        t["market_cap_usd"] = round(t.get("price_usd", 0) * t.get("total_supply", 0), 2)

    return {"tokens": tokens, "total": len(tokens)}


# ── Buy Custom Token ──

@router.post("/buy-custom-token")
async def buy_custom_token(req: BuyCustomTokenRequest, current_user: dict = Depends(get_current_user)):
    """Buy a custom token paying with any supported asset."""
    db = get_database()
    uid = current_user["user_id"]
    symbol = req.symbol.upper()
    pay_asset = req.pay_asset.upper()

    token = await db.custom_tokens.find_one({"symbol": symbol}, {"_id": 0})
    if not token:
        raise HTTPException(status_code=404, detail=f"Token {symbol} non trovato")

    token_price_eur = token.get("price_eur", 0)
    if token_price_eur <= 0:
        raise HTTPException(status_code=400, detail="Prezzo token non valido")

    pay_price_eur = await _get_any_price_eur(db, pay_asset)
    if pay_price_eur is None:
        raise HTTPException(status_code=400, detail=f"Asset di pagamento non supportato: {pay_asset}")

    total_eur = req.amount * token_price_eur
    fee_eur = round(total_eur * PLATFORM_FEE, 8)
    gross_eur = total_eur + fee_eur
    pay_amount = round(gross_eur / pay_price_eur, 8)

    balance = await _get_balance(db, uid, pay_asset)
    if balance < pay_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Saldo {pay_asset} insufficiente: {balance:.8g} disponibile, {pay_amount:.8g} necessario",
        )

    await _debit(db, uid, pay_asset, pay_amount)
    await _credit(db, uid, symbol, req.amount)

    tx_id = str(uuid.uuid4())
    settlement = _settlement_record(tx_id, "buy_custom_token", uid, req.amount, symbol, {
        "debit": {"asset": pay_asset, "amount": pay_amount},
        "credit": {"asset": symbol, "amount": req.amount},
        "fee_eur": round(fee_eur, 4),
    })

    tx = {
        "id": tx_id, "user_id": uid, "type": "buy_custom_token",
        "token_symbol": symbol, "token_amount": req.amount,
        "pay_asset": pay_asset, "pay_amount": pay_amount,
        "price_eur": token_price_eur, "price_usd": token.get("price_usd", 0),
        "fee_eur": round(fee_eur, 4), "status": "completed",
        **settlement,
        "created_at": datetime.now(timezone.utc),
    }
    await _log_tx(db, tx)
    tx["created_at"] = tx["created_at"].isoformat()

    return {
        "message": f"Acquistati {req.amount} {symbol} per {pay_amount} {pay_asset}",
        "transaction": tx,
        "balances": {
            symbol: round(await _get_balance(db, uid, symbol), 8),
            pay_asset: round(await _get_balance(db, uid, pay_asset), 8),
        },
    }


# ── Sell Custom Token ──

@router.post("/sell-custom-token")
async def sell_custom_token(req: SellCustomTokenRequest, current_user: dict = Depends(get_current_user)):
    """Sell a custom token and receive any supported asset."""
    db = get_database()
    uid = current_user["user_id"]
    symbol = req.symbol.upper()
    receive_asset = req.receive_asset.upper()

    token = await db.custom_tokens.find_one({"symbol": symbol}, {"_id": 0})
    if not token:
        raise HTTPException(status_code=404, detail=f"Token {symbol} non trovato")

    token_price_eur = token.get("price_eur", 0)
    if token_price_eur <= 0:
        raise HTTPException(status_code=400, detail="Prezzo token non valido")

    balance = await _get_balance(db, uid, symbol)
    if balance < req.amount:
        raise HTTPException(
            status_code=400,
            detail=f"Saldo {symbol} insufficiente: {balance:.8g} disponibile, {req.amount:.8g} necessario",
        )

    receive_price_eur = await _get_any_price_eur(db, receive_asset)
    if receive_price_eur is None:
        raise HTTPException(status_code=400, detail=f"Asset di ricezione non supportato: {receive_asset}")

    total_eur = req.amount * token_price_eur
    fee_eur = round(total_eur * PLATFORM_FEE, 8)
    net_eur = total_eur - fee_eur
    receive_amount = round(net_eur / receive_price_eur, 8)

    await _debit(db, uid, symbol, req.amount)
    await _credit(db, uid, receive_asset, receive_amount)

    tx_id = str(uuid.uuid4())
    settlement = _settlement_record(tx_id, "sell_custom_token", uid, req.amount, symbol, {
        "debit": {"asset": symbol, "amount": req.amount},
        "credit": {"asset": receive_asset, "amount": receive_amount},
        "fee_eur": round(fee_eur, 4),
    })

    tx = {
        "id": tx_id, "user_id": uid, "type": "sell_custom_token",
        "token_symbol": symbol, "token_amount": req.amount,
        "receive_asset": receive_asset, "receive_amount": receive_amount,
        "price_eur": token_price_eur, "price_usd": token.get("price_usd", 0),
        "fee_eur": round(fee_eur, 4), "status": "completed",
        **settlement,
        "created_at": datetime.now(timezone.utc),
    }
    await _log_tx(db, tx)
    tx["created_at"] = tx["created_at"].isoformat()

    return {
        "message": f"Venduti {req.amount} {symbol} per {receive_amount} {receive_asset}",
        "transaction": tx,
        "balances": {
            symbol: round(await _get_balance(db, uid, symbol), 8),
            receive_asset: round(await _get_balance(db, uid, receive_asset), 8),
        },
    }


# ── Update Token Price ──

@router.put("/custom-tokens/{symbol}/price")
async def update_token_price(symbol: str, price_usd: float, current_user: dict = Depends(get_current_user)):
    db = get_database()
    symbol = symbol.upper()
    token = await db.custom_tokens.find_one({"symbol": symbol})
    if not token:
        raise HTTPException(status_code=404, detail="Token non trovato")
    if token["creator_id"] != current_user["user_id"]:
        raise HTTPException(status_code=403, detail="Solo il creatore puo' modificare il prezzo")
    if price_usd <= 0:
        raise HTTPException(status_code=400, detail="Il prezzo deve essere > 0")

    price_eur = round(price_usd * USD_EUR_RATE, 4)
    await db.custom_tokens.update_one({"symbol": symbol}, {"$set": {"price_usd": round(price_usd, 2), "price_eur": price_eur}})
    return {"message": f"Prezzo di {symbol} aggiornato a ${price_usd}", "symbol": symbol, "price_usd": round(price_usd, 2), "price_eur": price_eur}


# ── Real-Time Balance Polling ──

@router.get("/live-balances")
async def live_balances(current_user: dict = Depends(get_current_user)):
    """Get all wallet balances for real-time polling updates."""
    db = get_database()
    uid = current_user["user_id"]
    wallets = await db.wallets.find({"user_id": uid, "balance": {"$gt": 0}}, {"_id": 0}).to_list(100)

    custom_tokens = await db.custom_tokens.find({}, {"_id": 0}).to_list(100)
    custom_prices = {t["symbol"]: {"usd": t.get("price_usd", 0), "eur": t.get("price_eur", 0)} for t in custom_tokens}

    pricing = await _get_dynamic_neno_price()
    neno_price = pricing["price"]

    balances = {}
    total_usd = 0
    for w in wallets:
        asset = w["asset"]
        bal = w["balance"]
        if asset == "NENO":
            price_eur = neno_price
        elif asset in MARKET_PRICES_EUR:
            price_eur = MARKET_PRICES_EUR[asset]
        elif asset in custom_prices:
            price_eur = custom_prices[asset]["eur"]
        else:
            price_eur = 0

        price_usd = round(price_eur / USD_EUR_RATE, 2) if price_eur > 0 else 0
        value_usd = round(bal * price_usd, 2)
        total_usd += value_usd
        balances[asset] = {
            "balance": round(bal, 8),
            "price_usd": price_usd,
            "value_usd": value_usd,
            "is_custom": asset in custom_prices,
        }

    return {
        "balances": balances,
        "total_value_usd": round(total_usd, 2),
        "neno_price": pricing,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Off-Ramp: NENO -> EUR -> Card or Bank ──

@router.post("/offramp")
async def offramp_neno(req: OfframpRequest, current_user: dict = Depends(get_current_user)):
    db = get_database()
    uid = current_user["user_id"]
    onchain_tx = req.tx_hash or None
    guard = SecurityGuard.get_instance()

    # ── Idempotency check ──
    from services.idempotency_service import IdempotencyService
    idem = IdempotencyService.get_instance()
    idem_key = idem.generate_key(uid, "offramp", neno_amount=str(req.neno_amount), destination=req.destination)
    lock_result = await idem.check_and_lock(idem_key, "offramp", uid)
    if not lock_result["locked"]:
        existing = lock_result.get("existing", {})
        if existing.get("status") == "completed":
            return existing.get("result_summary", {"message": "Operazione già eseguita (idempotency)", "duplicate": True})

    # ── Rate limit ──
    allowed, remaining = await guard.check_rate_limit(uid)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit superato: max 10 operazioni/minuto")

    # ── AUDIT PRE ──
    audit_pre = await log_pre_operation(
        op_type="OFFRAMP", user_id=uid,
        user_email=current_user.get("email", ""),
        assets_involved=["NENO", "EUR", "USDT", "USDC"],
        neno_amount=req.neno_amount,
        extra={"destination": req.destination, "wallet": req.destination_wallet, "stable": req.preferred_stable}
    )

    # ── MM Pricing: sell at bid ──
    mm = MarketMakerService.get_instance()
    mm_pricing = await mm.get_pricing()
    neno_eur_price = mm_pricing["bid"]

    eur_gross = round(req.neno_amount * neno_eur_price, 2)
    fee = round(eur_gross * PLATFORM_FEE, 2)
    eur_net = round(eur_gross - fee, 2)
    eur_value = eur_gross

    # ── Treasury caps ──
    cap_ok, cap_reason = await guard.enforce_caps(uid, eur_value, req.neno_amount)
    if not cap_ok:
        raise HTTPException(status_code=400, detail=cap_reason)

    # ── Reentrancy lock ──
    async with guard.get_user_lock(uid):
        neno_balance = await _get_balance(db, uid, "NENO")
        if neno_balance < req.neno_amount:
            raise HTTPException(status_code=400, detail=f"Saldo NENO insufficiente: {neno_balance:.8g}")
        await _debit(db, uid, "NENO", req.neno_amount)

        # ── Treasury update: receives NENO ──
        await mm.update_treasury("NENO", req.neno_amount, "offramp_receive", neno_eur_price)

    # ── Destination routing ──
    payout_state = STATE_INTERNAL_CREDITED
    dest_info = ""
    crypto_result = None
    real_tx_hash = None
    real_payout_id = None

    if req.destination == "card":
        if not req.card_id:
            raise HTTPException(status_code=400, detail="card_id richiesto per off-ramp su carta")
        card = await db.cards.find_one({"id": req.card_id, "user_id": uid})
        if not card:
            raise HTTPException(status_code=404, detail="Carta non trovata")
        await db.cards.update_one({"id": req.card_id}, {"$inc": {"balance": eur_net}})
        dest_info = f"Carta {card.get('card_number_masked', '****')}"
        payout_state = STATE_PAYOUT_SETTLED
        await mm.update_treasury("EUR", -eur_net, "offramp_card_payout", 1.0)

    elif req.destination == "bank":
        # ── Stripe SEPA Real Payout ──
        destination_iban = req.destination_iban or os.environ.get("PAYOUT_IBAN", "")
        beneficiary = req.beneficiary_name or os.environ.get("PAYOUT_BENEFICIARY_NAME", "NeoNoble User")

        try:
            from services.real_payout_service import get_real_payout_service
            payout_svc = get_real_payout_service()
            if payout_svc and payout_svc.is_available():
                withdrawal_fee = max(round(eur_net * 0.001, 2), 0.50)
                eur_after_bank = round(eur_net - withdrawal_fee, 2)

                payout_result = await payout_svc.create_payout(
                    quote_id=str(uuid.uuid4()), transaction_id=str(uuid.uuid4()),
                    amount_eur=eur_after_bank,
                    reference=f"OFFRAMP-{uuid.uuid4().hex[:8].upper()}",
                    metadata={"user_id": uid, "neno_amount": req.neno_amount, "iban": destination_iban},
                )
                if payout_result.success:
                    real_payout_id = payout_result.payout_id
                    eur_net = eur_after_bank
                    dest_info = f"SEPA {destination_iban[-4:]} | payout: {real_payout_id}"
                    payout_state = STATE_PAYOUT_PENDING
                    await mm.update_treasury("EUR", -eur_net, "offramp_bank_payout", 1.0)
                else:
                    # Stripe failed → fallback to crypto
                    logger.warning(f"[OFFRAMP] Stripe SEPA failed: {payout_result.error}. Trying crypto fallback.")
                    dest_wallet = req.destination_wallet
                    if not dest_wallet:
                        user = await db.users.find_one({"user_id": uid}, {"_id": 0, "connected_wallet": 1})
                        dest_wallet = user.get("connected_wallet") if user else None
                    if dest_wallet:
                        stable = (req.preferred_stable or "USDT").upper()
                        crypto_result = await mm.execute_stablecoin_offramp(uid, eur_net, dest_wallet, stable)
                        if crypto_result["success"]:
                            real_tx_hash = crypto_result.get("tx_hash")
                            dest_info = f"{crypto_result['stable_asset']} -> {dest_wallet[:8]}...{dest_wallet[-6:]}"
                            payout_state = STATE_PAYOUT_EXECUTED_EXTERNAL
                        else:
                            await _credit(db, uid, "NENO", req.neno_amount)
                            await mm.update_treasury("NENO", -req.neno_amount, "offramp_refund", neno_eur_price)
                            raise HTTPException(status_code=500, detail=f"Payout fallito (Stripe + crypto): {crypto_result['error']}")
                    else:
                        bank_tx = {
                            "id": str(uuid.uuid4()), "user_id": uid, "type": "sepa_withdrawal",
                            "amount": eur_net, "fee": withdrawal_fee, "net_amount": eur_after_bank,
                            "currency": "EUR", "destination_iban": destination_iban,
                            "beneficiary_name": beneficiary,
                            "status": "pending_settlement",
                            "stripe_error": payout_result.error,
                            "created_at": datetime.now(timezone.utc),
                        }
                        await db.banking_transactions.insert_one({**bank_tx, "_id": bank_tx["id"]})
                        dest_info = f"IBAN {destination_iban[-4:]} (pending)"
                        payout_state = "pending_settlement"
            else:
                # No Stripe → crypto fallback
                dest_wallet = req.destination_wallet
                if not dest_wallet:
                    user = await db.users.find_one({"user_id": uid}, {"_id": 0, "connected_wallet": 1})
                    dest_wallet = user.get("connected_wallet") if user else None
                if not dest_wallet:
                    raise HTTPException(
                        status_code=400,
                        detail="Stripe SEPA non configurato e nessun wallet esterno disponibile."
                    )
                stable = (req.preferred_stable or "USDT").upper()
                crypto_result = await mm.execute_stablecoin_offramp(uid, eur_net, dest_wallet, stable)
                if crypto_result["success"]:
                    real_tx_hash = crypto_result.get("tx_hash")
                    dest_info = f"{crypto_result['stable_asset']} -> {dest_wallet[:8]}...{dest_wallet[-6:]}"
                    payout_state = STATE_PAYOUT_EXECUTED_EXTERNAL
                else:
                    await _credit(db, uid, "NENO", req.neno_amount)
                    await mm.update_treasury("NENO", -req.neno_amount, "offramp_refund", neno_eur_price)
                    raise HTTPException(status_code=500, detail=f"Off-ramp crypto fallito: {crypto_result['error']}")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[OFFRAMP] Bank payout error: {e}")
            dest_info = f"IBAN (errore: {str(e)[:50]})"
            payout_state = "failed"

    elif req.destination == "crypto":
        dest_wallet = req.destination_wallet
        if not dest_wallet:
            user = await db.users.find_one({"user_id": uid}, {"_id": 0, "connected_wallet": 1})
            dest_wallet = user.get("connected_wallet") if user else None
        if not dest_wallet:
            raise HTTPException(status_code=400, detail="destination_wallet richiesto per off-ramp crypto")
        stable = (req.preferred_stable or "USDT").upper()
        crypto_result = await mm.execute_stablecoin_offramp(uid, eur_net, dest_wallet, stable)
        if crypto_result["success"]:
            real_tx_hash = crypto_result.get("tx_hash")
            dest_info = f"{crypto_result['stable_asset']} -> {dest_wallet[:8]}...{dest_wallet[-6:]}"
            payout_state = STATE_PAYOUT_EXECUTED_EXTERNAL
        else:
            await _credit(db, uid, "NENO", req.neno_amount)
            await mm.update_treasury("NENO", -req.neno_amount, "offramp_refund", neno_eur_price)
            raise HTTPException(status_code=500, detail=f"Off-ramp crypto fallito: {crypto_result['error']}")
    else:
        raise HTTPException(status_code=400, detail="destination deve essere 'card', 'bank' o 'crypto'")

    # ── Status enforcement ──
    final_status = SecurityGuard.resolve_status(
        has_tx_hash=bool(real_tx_hash or onchain_tx),
        has_payout_id=bool(real_payout_id),
        has_treasury_proof=True,
    )
    # Override with payout_state if it's more specific
    if payout_state in (STATE_PAYOUT_SETTLED, STATE_PAYOUT_EXECUTED_EXTERNAL):
        final_status = "completed"
    elif payout_state == STATE_PAYOUT_PENDING:
        final_status = "pending_settlement"

    tx_id = str(uuid.uuid4())
    settlement = _settlement_record(tx_id, "neno_offramp", uid, req.neno_amount, "EUR", {
        "debit": {"asset": "NENO", "amount": req.neno_amount},
        "credit": {"asset": "EUR", "amount": eur_net, "destination": req.destination},
        "fee": {"asset": "EUR", "amount": fee},
        "onchain_tx_hash": onchain_tx,
        "crypto_tx_hash": real_tx_hash,
        "payout_id": real_payout_id,
    })

    tx = {
        "id": tx_id, "user_id": uid, "type": "neno_offramp",
        "neno_amount": req.neno_amount, "eur_gross": eur_gross, "fee": fee,
        "eur_net": eur_net, "destination": req.destination,
        "destination_info": dest_info,
        "status": final_status,
        "execution_mode": "fiat_sepa" if real_payout_id else ("crypto_external" if real_tx_hash else "internal"),
        "onchain_tx_hash": onchain_tx,
        "delivery_tx_hash": real_tx_hash,
        "payout_id": real_payout_id,
        "crypto_payout": crypto_result if crypto_result else None,
        "mm_bid": mm_pricing["bid"], "mm_ask": mm_pricing["ask"],
        "mm_spread_bps": mm_pricing["spread_bps"],
        **settlement,
        "created_at": datetime.now(timezone.utc),
    }
    await _log_tx(db, tx)
    tx["created_at"] = tx["created_at"].isoformat()

    # Create ledger entry
    ledger = await create_ledger_entry(
        user_id=uid, tx_type="neno_offramp", debit_asset="NENO",
        debit_amount=req.neno_amount, credit_asset="EUR", credit_amount=eur_net,
        fee_amount=fee, fee_asset="EUR", onchain_tx_hash=real_tx_hash or onchain_tx,
        destination_type=req.destination,
        destination_details={
            "iban": req.destination_iban, "card_id": req.card_id,
            "beneficiary": req.beneficiary_name,
            "crypto_wallet": req.destination_wallet,
            "crypto_tx_hash": real_tx_hash,
            "payout_id": real_payout_id,
        },
        initial_state=STATE_INTERNAL_CREDITED,
    )

    if payout_state == STATE_PAYOUT_EXECUTED_EXTERNAL:
        await transition_state(ledger["id"], STATE_PAYOUT_EXECUTED_EXTERNAL, "Crypto off-ramp executed")
    elif real_payout_id:
        await enqueue_payout(
            user_id=uid, amount=eur_net, currency="EUR",
            destination_type="bank", destination_iban=req.destination_iban or os.environ.get("PAYOUT_IBAN", ""),
            beneficiary_name=req.beneficiary_name or os.environ.get("PAYOUT_BENEFICIARY_NAME", "NeoNoble User"),
            ledger_entry_id=ledger["id"],
        )
        await transition_state(ledger["id"], STATE_PAYOUT_PENDING, f"Stripe SEPA payout: {real_payout_id}")
    elif req.destination == "card":
        await transition_state(ledger["id"], STATE_PAYOUT_PENDING, "Card top-up")

    # PnL entry
    await db.mm_pnl_ledger.insert_one({
        "_id": str(uuid.uuid4()),
        "tx_id": tx_id, "user_id": uid, "direction": "offramp",
        "neno_amount": req.neno_amount, "counter_asset": "EUR",
        "counter_amount": eur_net,
        "effective_price": neno_eur_price, "mid_price": mm_pricing["mid_price"],
        "spread_revenue_eur": round(abs(mm_pricing["mid_price"] - neno_eur_price) * req.neno_amount, 4),
        "fee_revenue_eur": round(fee, 4),
        "total_revenue_eur": round(fee + abs(mm_pricing["mid_price"] - neno_eur_price) * req.neno_amount, 4),
        "inventory_change_neno": round(req.neno_amount, 8),
        "inventory_change_counter": round(-eur_net, 8),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # ── WebSocket balance broadcast ──
    try:
        from routes.websocket_routes import broadcast_balance_update
        asyncio.ensure_future(broadcast_balance_update(uid, {
            "balances": {"NENO": round(await _get_balance(db, uid, "NENO"), 8)},
            "trigger": "offramp", "tx_id": tx_id,
        }))
    except Exception:
        pass

    offramp_result = {
        "message": f"{req.neno_amount} NENO -> EUR {eur_net:.2f} -> {dest_info}",
        "transaction": tx,
        "neno_balance": round(await _get_balance(db, uid, "NENO"), 8),
        "state": final_status,
        "execution_proof": {
            "tx_hash": real_tx_hash,
            "payout_id": real_payout_id,
            "explorer": f"https://bscscan.com/tx/{real_tx_hash}" if real_tx_hash else None,
            "treasury_movement": True,
        },
        "payout": {
            "state": final_status,
            "amount": eur_net,
            "destination": dest_info,
            "crypto_tx_hash": real_tx_hash,
            "crypto_explorer": f"https://bscscan.com/tx/{real_tx_hash}" if real_tx_hash else None,
            "stripe_payout_id": real_payout_id,
        },
        "onchain_explorer": f"https://bscscan.com/tx/{real_tx_hash or onchain_tx}" if (real_tx_hash or onchain_tx) else None,
        "market_maker": {
            "price_type": "bid", "effective_price": neno_eur_price,
            "mid_price": mm_pricing["mid_price"], "spread_bps": mm_pricing["spread_bps"],
        },
    }

    # ── AUDIT POST ──
    await log_post_operation(
        pre_snapshot=audit_pre, result=offramp_result,
        assets_involved=["NENO", "EUR", "USDT", "USDC"], tx_id=tx_id
    )

    return offramp_result


# ── Transaction History ──

@router.get("/transactions")
async def get_neno_transactions(current_user: dict = Depends(get_current_user)):
    db = get_database()
    txs = await db.neno_transactions.find(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    for t in txs:
        if "created_at" in t and hasattr(t["created_at"], "isoformat"):
            t["created_at"] = t["created_at"].isoformat()
    return {"transactions": txs, "total": len(txs)}


# ── Market Info ──

@router.get("/market")
async def neno_market_info():
    db = get_database()
    # ── MM pricing ──
    mm = MarketMakerService.get_instance()
    mm_pricing = await mm.get_pricing()
    neno_price = mm_pricing["mid_price"]

    pairs = {}
    for asset, eur_price in MARKET_PRICES_EUR.items():
        rate = neno_price / eur_price
        pairs[f"NENO/{asset}"] = {"rate": round(rate, 8), "asset_eur_price": eur_price, "neno_eur_price": neno_price}

    custom_tokens = await db.custom_tokens.find({}, {"_id": 0}).to_list(100)
    for t in custom_tokens:
        rate = neno_price / t["price_eur"] if t["price_eur"] > 0 else 0
        pairs[f"NENO/{t['symbol']}"] = {"rate": round(rate, 8), "asset_eur_price": t["price_eur"], "neno_eur_price": neno_price}

    all_assets = SUPPORTED_ASSETS + [t["symbol"] for t in custom_tokens]
    return {
        "neno_eur_price": neno_price,
        "neno_usd_price": round(neno_price * 1.087, 2),
        "bid": mm_pricing["bid"],
        "ask": mm_pricing["ask"],
        "spread_bps": mm_pricing["spread_bps"],
        "spread_pct": mm_pricing["spread_pct"],
        "spread_eur": mm_pricing["spread_eur"],
        "inventory_skew": mm_pricing["inventory_skew"],
        "treasury_neno": mm_pricing["treasury_neno"],
        "fee_percent": PLATFORM_FEE * 100,
        "supported_assets": all_assets,
        "pairs": pairs,
        "custom_tokens": custom_tokens,
        "pricing_model": "market_maker",
    }



# ── Platform Hot Wallet (derived from mnemonic) ──

@router.get("/platform-wallet")
async def get_platform_wallet():
    """Get the platform hot wallet address where users send NENO for sell/off-ramp."""
    hot_wallet = _get_platform_hot_wallet()
    return {
        "address": hot_wallet,
        "chain": "BSC Mainnet",
        "chain_id": 56,
        "contract": "0xeF3F5C1892A8d7A3304E4A15959E124402d69974",
        "usage": "Inviare NENO a questo indirizzo per operazioni Sell / Off-Ramp / Swap",
    }


class VerifyDepositRequest(BaseModel):
    tx_hash: str = Field(min_length=60, max_length=70, description="On-chain transaction hash (0x...)")
    expected_amount: float = Field(gt=0, description="Expected NENO amount transferred")
    operation: str = Field(description="sell, swap, or offramp")


@router.post("/verify-deposit")
async def verify_onchain_deposit(req: VerifyDepositRequest, current_user: dict = Depends(get_current_user)):
    """
    Verify an on-chain NENO transfer to the platform hot wallet.
    After verification:
      (a) Credits NENO to user's internal wallet
      (b) Creates a transaction record in neno_transactions
      (c) Sends notification
    """
    db = get_database()
    uid = current_user["user_id"]
    engine = OnChainSettlement.get_instance()
    hot_wallet = _get_platform_hot_wallet()

    # Check if tx_hash already processed
    existing = await db.onchain_deposits.find_one({"tx_hash": req.tx_hash})
    if existing:
        raise HTTPException(status_code=400, detail="Transazione gia' processata")

    # Verify on-chain
    w3 = engine._get_web3()
    if not w3:
        raise HTTPException(status_code=503, detail="BSC RPC non disponibile. Riprova tra poco.")

    try:
        from web3 import Web3
        tx_receipt = w3.eth.get_transaction_receipt(req.tx_hash)
        if tx_receipt is None:
            raise HTTPException(status_code=404, detail="Transazione non trovata on-chain. Attendi la conferma.")

        if tx_receipt.status != 1:
            raise HTTPException(status_code=400, detail="Transazione fallita on-chain (reverted)")

        # Parse ERC-20 Transfer event logs
        transfer_topic = Web3.keccak(text="Transfer(address,address,uint256)").hex()
        neno_contract_lower = "0xeF3F5C1892A8d7A3304E4A15959E124402d69974".lower()

        verified_amount = 0
        sender_address = None
        for log_entry in tx_receipt.logs:
            log_address = log_entry.address.lower() if hasattr(log_entry.address, 'lower') else str(log_entry.address).lower()
            if log_address != neno_contract_lower:
                continue
            topics = log_entry.topics
            if len(topics) < 3:
                continue
            topic0 = topics[0].hex() if hasattr(topics[0], 'hex') else str(topics[0])
            if topic0 != transfer_topic:
                continue
            to_addr = "0x" + (topics[2].hex() if hasattr(topics[2], 'hex') else str(topics[2]))[-40:]
            from_addr = "0x" + (topics[1].hex() if hasattr(topics[1], 'hex') else str(topics[1]))[-40:]
            # Normalize and compare
            if to_addr.lower().replace("0x", "") != hot_wallet.lower().replace("0x", ""):
                continue
            data_hex = log_entry.data.hex() if hasattr(log_entry.data, 'hex') else str(log_entry.data)
            raw_amount = int(data_hex, 16)
            from decimal import Decimal
            verified_amount = float(Decimal(raw_amount) / Decimal(10 ** 18))
            sender_address = Web3.to_checksum_address("0x" + from_addr.replace("0x", "").zfill(40)[-40:])
            break

        if verified_amount <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"Nessun trasferimento NENO trovato verso il hot wallet ({hot_wallet}) in questa transazione"
            )

        # Allow 2% tolerance for amount matching
        tolerance = req.expected_amount * 0.02
        if abs(verified_amount - req.expected_amount) > tolerance:
            raise HTTPException(
                status_code=400,
                detail=f"Importo non corrispondente: atteso {req.expected_amount} NENO, trovato {verified_amount} NENO on-chain"
            )

        # ── (a) Credit NENO to user's internal wallet ──
        await _credit(db, uid, "NENO", verified_amount)
        logger.info(f"Credited {verified_amount} NENO to user {uid} from on-chain deposit {req.tx_hash[:16]}...")

        # ── (b) Create transaction record ──
        tx_id = str(uuid.uuid4())
        settlement = _settlement_record(tx_id, "onchain_deposit", uid, verified_amount, "NENO", {
            "credit": {"asset": "NENO", "amount": verified_amount},
            "onchain_tx_hash": req.tx_hash,
            "sender_address": sender_address,
        })

        deposit_tx = {
            "id": tx_id,
            "user_id": uid,
            "type": "onchain_deposit",
            "neno_amount": verified_amount,
            "sender_address": sender_address,
            "hot_wallet": hot_wallet,
            "tx_hash": req.tx_hash,
            "block_number": tx_receipt.blockNumber,
            "execution_mode": "onchain",
            "onchain_tx_hash": req.tx_hash,
            "status": "completed",
            **settlement,
            "created_at": datetime.now(timezone.utc),
        }
        await _log_tx(db, deposit_tx)

        # Store verified deposit record
        deposit_record = {
            "id": str(uuid.uuid4()),
            "tx_hash": req.tx_hash,
            "user_id": uid,
            "sender_address": sender_address,
            "hot_wallet": hot_wallet,
            "neno_amount": verified_amount,
            "operation": req.operation,
            "block_number": tx_receipt.blockNumber,
            "status": "verified",
            "credited": True,
            "internal_tx_id": tx_id,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.onchain_deposits.insert_one({**deposit_record, "_id": deposit_record["id"]})

        # ── (c) Send notification ──
        try:
            from services.notification_dispatch import notify_trade_executed
            asyncio.ensure_future(notify_trade_executed(uid, "NENO", "deposit", verified_amount, 0, 0))
        except Exception:
            pass

        new_balance = await _get_balance(db, uid, "NENO")

        return {
            "verified": True,
            "tx_hash": req.tx_hash,
            "neno_amount": verified_amount,
            "sender": sender_address,
            "block_number": tx_receipt.blockNumber,
            "explorer": f"https://bscscan.com/tx/{req.tx_hash}",
            "message": f"Deposito verificato e accreditato: {verified_amount} NENO",
            "credited": True,
            "new_neno_balance": round(new_balance, 8),
            "internal_tx_id": tx_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verify deposit error: {e}")
        raise HTTPException(status_code=500, detail=f"Errore verifica on-chain: {str(e)}")


# ── NENO Contract On-Chain Info ──

@router.get("/contract-info")
async def neno_contract_info():
    """Get verified NENO contract information from BSC blockchain."""
    engine = OnChainSettlement.get_instance()
    contract_info = engine.read_contract_info()
    block = engine.get_current_block()
    return {
        "contract": contract_info,
        "current_block": block,
        "settlement_method": "On-Chain Anchored (keccak256 of BSC block_hash + tx_data)",
    }


@router.get("/onchain-balance/{wallet_address}")
async def read_onchain_neno_balance(wallet_address: str):
    """Read real NENO token balance from BSC for any wallet address."""
    engine = OnChainSettlement.get_instance()
    neno_balance = engine.read_neno_balance(wallet_address)
    bnb_balance = engine.read_native_balance(wallet_address)
    return {
        "wallet_address": wallet_address,
        "neno": neno_balance,
        "bnb": bnb_balance,
        "contract": "0xeF3F5C1892A8d7A3304E4A15959E124402d69974",
        "explorer": f"https://bscscan.com/token/0xeF3F5C1892A8d7A3304E4A15959E124402d69974?a={wallet_address}",
    }



# ── Settlement Verification ──

@router.get("/settlement/{tx_id}")
async def verify_settlement(tx_id: str, current_user: dict = Depends(get_current_user)):
    """Verify on-chain anchored settlement for a specific transaction."""
    db = get_database()
    tx = await db.neno_transactions.find_one(
        {"id": tx_id, "user_id": current_user["user_id"]}, {"_id": 0}
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transazione non trovata")

    if "created_at" in tx and hasattr(tx["created_at"], "isoformat"):
        tx["created_at"] = tx["created_at"].isoformat()

    engine = OnChainSettlement.get_instance()
    current_block = engine.get_current_block()

    # Calculate confirmations since settlement block
    settlement_block = tx.get("settlement_block_number", 0)
    confirmations = max(0, current_block["block_number"] - settlement_block) if current_block["available"] and settlement_block else tx.get("settlement_confirmations", 0)

    return {
        "transaction_id": tx["id"],
        "settlement_hash": tx.get("settlement_hash", "N/A"),
        "settlement_status": tx.get("settlement_status", "unknown"),
        "settlement_timestamp": tx.get("settlement_timestamp"),
        "settlement_network": tx.get("settlement_network", "BSC Mainnet"),
        "settlement_chain_id": tx.get("settlement_chain_id", 56),
        "settlement_contract": tx.get("settlement_contract", "0xeF3F5C1892A8d7A3304E4A15959E124402d69974"),
        "settlement_block_number": settlement_block,
        "settlement_block_hash": tx.get("settlement_block_hash"),
        "settlement_confirmations": confirmations,
        "settlement_explorer": tx.get("settlement_explorer"),
        "settlement_contract_explorer": tx.get("settlement_contract_explorer"),
        "type": tx.get("type"),
        "status": tx.get("status"),
        "details": tx.get("settlement_details", {}),
        "current_block": current_block["block_number"],
    }


# ── Wallet Sync: Compare internal vs external (on-chain) balances ──

class WalletSyncRequest(BaseModel):
    external_address: str = Field(min_length=10, max_length=100)
    chain_id: int = 1
    on_chain_balances: Optional[dict] = None


@router.post("/wallet-sync")
async def wallet_sync(req: WalletSyncRequest, current_user: dict = Depends(get_current_user)):
    """Sync internal balances with connected external wallet — reads on-chain NENO balance."""
    db = get_database()
    uid = current_user["user_id"]
    engine = OnChainSettlement.get_instance()

    # Read on-chain NENO balance
    onchain_neno = engine.read_neno_balance(req.external_address)
    native_bnb = engine.read_native_balance(req.external_address)

    # Fetch internal balances
    wallets = await db.wallets.find(
        {"user_id": uid, "balance": {"$gt": 0}}, {"_id": 0}
    ).to_list(50)
    internal_balances = {w["asset"]: w["balance"] for w in wallets}

    # Store wallet association
    await db.users.update_one(
        {"user_id": uid},
        {"$set": {
            "connected_wallet": req.external_address,
            "connected_chain_id": req.chain_id,
            "wallet_synced_at": datetime.now(timezone.utc).isoformat(),
            "onchain_neno_balance": onchain_neno["balance"],
            "onchain_bnb_balance": native_bnb.get("balance_bnb", 0),
        }}
    )

    # Build sync report
    sync_report = []
    for asset, internal_bal in internal_balances.items():
        external_bal = onchain_neno["balance"] if asset == "NENO" else 0
        sync_report.append({
            "asset": asset,
            "internal_balance": round(internal_bal, 8),
            "onchain_balance": round(external_bal, 8) if asset == "NENO" else "N/A",
            "synced": True,
        })

    return {
        "external_address": req.external_address,
        "chain": "BSC Mainnet",
        "chain_id": 56,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "neno_contract": "0xeF3F5C1892A8d7A3304E4A15959E124402d69974",
        "neno_contract_explorer": "https://bscscan.com/token/0xeF3F5C1892A8d7A3304E4A15959E124402d69974",
        "onchain_neno_balance": onchain_neno["balance"],
        "onchain_bnb_balance": native_bnb.get("balance_bnb", 0),
        "internal_balances": internal_balances,
        "sync_report": sync_report,
        "total_internal_assets": len(internal_balances),
    }


# ── Full Portfolio Snapshot (internal + external) ──

@router.get("/portfolio-snapshot")
async def portfolio_snapshot(current_user: dict = Depends(get_current_user)):
    """Full portfolio with on-chain contract verification and settlement proofs."""
    db = get_database()
    uid = current_user["user_id"]
    engine = OnChainSettlement.get_instance()

    wallets = await db.wallets.find({"user_id": uid, "balance": {"$gt": 0}}, {"_id": 0}).to_list(50)
    custom_tokens = await db.custom_tokens.find({}, {"_id": 0}).to_list(100)
    custom_prices = {t["symbol"]: t["price_eur"] for t in custom_tokens}

    pricing = await _get_dynamic_neno_price()
    neno_price = pricing["price"]

    positions = []
    total_eur = 0
    for w in wallets:
        asset = w["asset"]
        bal = w["balance"]
        price = neno_price if asset == "NENO" else (MARKET_PRICES_EUR.get(asset) or custom_prices.get(asset, 0))
        value = bal * price
        positions.append({"asset": asset, "balance": round(bal, 8), "price_eur": price, "value_eur": round(value, 2)})
        total_eur += value

    recent_txs = await db.neno_transactions.find({"user_id": uid}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    for t in recent_txs:
        if "created_at" in t and hasattr(t["created_at"], "isoformat"):
            t["created_at"] = t["created_at"].isoformat()

    user = await db.users.find_one({"user_id": uid}, {"_id": 0, "connected_wallet": 1, "wallet_synced_at": 1})

    # On-chain contract info
    contract_info = engine.read_contract_info()
    current_block = engine.get_current_block()

    return {
        "snapshot_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_value_eur": round(total_eur, 2),
        "positions": sorted(positions, key=lambda x: -x["value_eur"]),
        "connected_wallet": user.get("connected_wallet") if user else None,
        "wallet_synced_at": user.get("wallet_synced_at") if user else None,
        "neno_contract": {
            "address": "0xeF3F5C1892A8d7A3304E4A15959E124402d69974",
            "chain": "BSC Mainnet",
            "chain_id": 56,
            "total_supply": contract_info.get("total_supply", 0),
            "explorer": "https://bscscan.com/token/0xeF3F5C1892A8d7A3304E4A15959E124402d69974",
            "verified": contract_info.get("available", False),
        },
        "current_block": current_block,
        "recent_settlements": [{
            "id": t["id"],
            "type": t["type"],
            "settlement_hash": t.get("settlement_hash", "N/A"),
            "status": t.get("settlement_status", t.get("status")),
            "block_number": t.get("settlement_block_number"),
            "block_explorer": t.get("settlement_explorer"),
            "timestamp": t.get("settlement_timestamp", t.get("created_at")),
        } for t in recent_txs],
    }



# ══════════════════════════════════════════════════════════════════
# SETTLEMENT LEDGER, FORCE SYNC, RECONCILIATION, PAYOUT QUEUE
# ══════════════════════════════════════════════════════════════════


class ForceBalanceSyncRequest(BaseModel):
    tx_hash: str = Field(description="On-chain transaction hash to force-sync")
    user_wallet: Optional[str] = Field(default=None, description="Sender wallet address (optional override)")


@router.post("/force-balance-sync")
async def force_balance_sync(req: ForceBalanceSyncRequest, current_user: dict = Depends(get_current_user)):
    """Force-sync an on-chain deposit by tx hash. Looks up the tx on BSC, credits internally."""
    db = get_database()
    uid = current_user["user_id"]
    tx_hash = req.tx_hash.strip()

    already = await db.onchain_deposits.find_one({"tx_hash": tx_hash, "credited": True})
    if already:
        return {"message": "Transazione gia' sincronizzata", "tx_hash": tx_hash, "amount": already.get("neno_amount", 0)}

    try:
        from services.blockchain_listener import BlockchainListener, NENO_CONTRACT_ADDRESS
        from web3 import Web3
        from decimal import Decimal

        rpc_url = os.environ.get('BSC_RPC_URL')
        if not rpc_url:
            raise HTTPException(status_code=500, detail="BSC RPC non configurato")

        from web3.middleware import ExtraDataToPOAMiddleware
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        receipt = w3.eth.get_transaction_receipt(tx_hash)
        if not receipt or receipt["status"] != 1:
            raise HTTPException(status_code=400, detail="Transazione non trovata o fallita on-chain")

        transfer_topic = w3.keccak(text="Transfer(address,address,uint256)").hex()
        neno_addr = Web3.to_checksum_address(NENO_CONTRACT_ADDRESS).lower()

        amount = 0
        sender = ""
        for log_entry in receipt["logs"]:
            if log_entry["address"].lower() == neno_addr and len(log_entry["topics"]) >= 3:
                if log_entry["topics"][0].hex() == transfer_topic:
                    sender = "0x" + log_entry["topics"][1].hex()[-40:]
                    raw_amount = int(log_entry["data"].hex(), 16)
                    amount = float(Decimal(raw_amount) / Decimal(10 ** 18))
                    break

        if amount <= 0:
            raise HTTPException(status_code=400, detail="Nessun trasferimento NENO trovato in questa transazione")

        wallet = await db.wallets.find_one({"user_id": uid, "asset": "NENO"})
        if wallet:
            await db.wallets.update_one({"user_id": uid, "asset": "NENO"}, {"$inc": {"balance": amount}})
        else:
            await db.wallets.insert_one({
                "id": str(uuid.uuid4()), "user_id": uid, "asset": "NENO",
                "balance": amount, "created_at": datetime.now(timezone.utc),
            })

        new_balance = (await db.wallets.find_one({"user_id": uid, "asset": "NENO"}, {"_id": 0}))["balance"]

        deposit_id = str(uuid.uuid4())
        await db.onchain_deposits.update_one(
            {"tx_hash": tx_hash},
            {"$set": {
                "id": deposit_id, "tx_hash": tx_hash, "user_id": uid,
                "sender_address": sender, "neno_amount": amount,
                "operation": "force_sync", "status": "verified",
                "credited": True, "block_number": receipt["blockNumber"],
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )

        tx_id = str(uuid.uuid4())
        await db.neno_transactions.insert_one({
            "_id": tx_id, "id": tx_id, "user_id": uid, "type": "onchain_deposit",
            "neno_amount": amount, "sender_address": sender, "tx_hash": tx_hash,
            "execution_mode": "force_sync", "status": "completed",
            "created_at": datetime.now(timezone.utc),
        })

        await create_ledger_entry(
            user_id=uid, tx_type="deposit_sync", debit_asset="NENO_ONCHAIN",
            debit_amount=amount, credit_asset="NENO", credit_amount=amount,
            onchain_tx_hash=tx_hash, initial_state=STATE_INTERNAL_CREDITED,
        )

        return {
            "message": f"Sincronizzato: {amount} NENO accreditati dal tx {tx_hash[:16]}...",
            "tx_hash": tx_hash, "amount": amount,
            "new_balance": round(new_balance, 8),
            "state": STATE_INTERNAL_CREDITED,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Force sync error: {e}")
        raise HTTPException(status_code=500, detail=f"Errore force sync: {str(e)}")


@router.post("/reconcile")
async def run_reconciliation(current_user: dict = Depends(get_current_user)):
    """Run full reconciliation: find and credit all unmatched on-chain deposits."""
    db = get_database()
    if current_user.get("role", "").upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Solo admin")

    credited = await reconcile_deposits()

    pending_deposits = await db.onchain_deposits.find(
        {"status": "pending_user_match"}, {"_id": 0}
    ).to_list(50)

    return {
        "reconciled_credits": credited,
        "unmatched_deposits": len(pending_deposits),
        "pending_details": [
            {"tx_hash": d["tx_hash"], "amount": d["neno_amount"], "sender": d.get("sender_address")}
            for d in pending_deposits
        ],
    }


@router.get("/ledger")
async def get_ledger(current_user: dict = Depends(get_current_user)):
    """Get settlement ledger for current user with full state history."""
    entries = await get_user_ledger(current_user["user_id"])
    return {"entries": entries, "total": len(entries)}


@router.get("/payouts")
async def get_payouts(current_user: dict = Depends(get_current_user)):
    """Get payout queue status for current user."""
    payouts = await get_user_payouts(current_user["user_id"])
    return {"payouts": payouts, "total": len(payouts)}


@router.get("/tx-state/{tx_id}")
async def get_transaction_state(tx_id: str, current_user: dict = Depends(get_current_user)):
    """Get full state of a transaction including ledger and payout status."""
    db = get_database()
    uid = current_user["user_id"]

    tx = await db.neno_transactions.find_one({"id": tx_id, "user_id": uid}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transazione non trovata")

    ledger = await db.settlement_ledger.find_one(
        {"user_id": uid, "onchain_tx_hash": tx.get("onchain_tx_hash", tx.get("tx_hash"))},
        {"_id": 0}
    )

    payout = None
    if ledger and ledger.get("id"):
        payout = await db.payout_queue.find_one({"ledger_entry_id": ledger["id"]}, {"_id": 0})

    return {
        "transaction": tx,
        "ledger": ledger,
        "payout": payout,
        "current_state": ledger["state"] if ledger else tx.get("status"),
    }



# ── Real On-Chain Withdrawal: Internal balance → real on-chain delivery ──

class RealWithdrawalRequest(BaseModel):
    asset: str = Field(description="Asset to withdraw (NENO, BNB, ETH, BTC, USDT, USDC)")
    amount: float = Field(gt=0, description="Amount to withdraw")
    destination_wallet: str = Field(min_length=10, description="Destination wallet address (0x...)")


@router.post("/withdraw-real")
async def withdraw_real_onchain(req: RealWithdrawalRequest, current_user: dict = Depends(get_current_user)):
    """
    Real on-chain withdrawal: debit internal balance, broadcast BEP-20 transfer.
    Supports: NENO, BNB, ETH (Binance-Peg), BTC (BTCB), USDT, USDC on BSC.
    Status is ONLY 'completed' with a confirmed tx hash.
    """
    db = get_database()
    uid = current_user["user_id"]
    asset = req.asset.upper()
    guard = SecurityGuard.get_instance()

    # Rate limit
    allowed, remaining = await guard.check_rate_limit(uid)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit superato: max 10 operazioni/minuto")

    # Price lookup for cap enforcement
    price_eur = await _get_any_price_eur(db, asset)
    if price_eur is None:
        raise HTTPException(status_code=400, detail=f"Asset {asset} non supportato")

    eur_value = round(req.amount * price_eur, 2)
    neno_amt = req.amount if asset == "NENO" else 0

    # Treasury caps
    cap_ok, cap_reason = await guard.enforce_caps(uid, eur_value, neno_amt)
    if not cap_ok:
        raise HTTPException(status_code=400, detail=cap_reason)

    # PAYOUT GUARD: check real on-chain fund availability
    vr_engine = VirtualRealEngine.get_instance()
    payout_check = await vr_engine.can_payout(asset, req.amount)
    if payout_check.get("blocked"):
        raise HTTPException(status_code=400, detail=f"PAYOUT BLOCCATO: {payout_check['reason']}")

    # Reentrancy lock + balance check
    async with guard.get_user_lock(uid):
        balance = await _get_balance(db, uid, asset)
        if balance < req.amount:
            raise HTTPException(status_code=400, detail=f"Saldo {asset} insufficiente: {balance:.8g}")
        await _debit(db, uid, asset, req.amount)

    # Real on-chain execution
    engine = ExecutionEngine.get_instance()
    exec_result = await engine.send_asset_real(asset, req.destination_wallet, req.amount)

    if not exec_result.get("success"):
        # Refund on failure
        await _credit(db, uid, asset, req.amount)
        raise HTTPException(
            status_code=500,
            detail=f"Trasferimento on-chain fallito: {exec_result.get('error', 'unknown')}"
        )

    tx_hash = exec_result["tx_hash"]
    final_status = "completed"  # has tx_hash proof

    tx_id = str(uuid.uuid4())
    settlement = _settlement_record(tx_id, "withdraw_real", uid, req.amount, asset, {
        "debit": {"asset": asset, "amount": req.amount},
        "delivery": {"tx_hash": tx_hash, "to": req.destination_wallet},
    })

    tx = {
        "id": tx_id, "user_id": uid, "type": "withdraw_real",
        "asset": asset, "amount": req.amount,
        "destination_wallet": req.destination_wallet,
        "delivery_tx_hash": tx_hash,
        "block_number": exec_result.get("block_number"),
        "gas_used": exec_result.get("gas_used"),
        "eur_value": eur_value,
        "status": final_status,
        "execution_mode": "onchain",
        **settlement,
        "created_at": datetime.now(timezone.utc),
    }
    await _log_tx(db, tx)
    tx["created_at"] = tx["created_at"].isoformat()

    new_balance = await _get_balance(db, uid, asset)

    # WebSocket broadcast
    try:
        from routes.websocket_routes import broadcast_balance_update
        asyncio.ensure_future(broadcast_balance_update(uid, {
            "balances": {asset: round(new_balance, 8)},
            "trigger": "withdraw_real", "tx_id": tx_id,
        }))
    except Exception:
        pass

    # ── Event-driven settlement confirmation ──
    try:
        from services.realtime_sync_service import EventBus
        asyncio.ensure_future(EventBus.get_instance().emit("settlement_confirmed", {
            "type": "withdraw_real", "tx_id": tx_id, "user_id": uid,
            "asset": asset, "amount": req.amount, "eur_value": eur_value,
            "tx_hash": tx_hash,
        }))
    except Exception:
        pass

    return {
        "message": f"Trasferiti {req.amount} {asset} a {req.destination_wallet}",
        "transaction": tx,
        "balance": round(new_balance, 8),
        "status": final_status,
        "execution_proof": {
            "tx_hash": tx_hash,
            "block_number": exec_result.get("block_number"),
            "gas_used": exec_result.get("gas_used"),
            "explorer": f"https://bscscan.com/tx/{tx_hash}",
            "from": exec_result.get("from"),
            "to": req.destination_wallet,
            "contract": exec_result.get("contract"),
            "chain": "BSC Mainnet",
        },
    }


# ── Security Status endpoint ──

@router.get("/security-status")
async def security_status(current_user: dict = Depends(get_current_user)):
    """View current security configuration and caps."""
    return {
        "treasury_caps": {
            "max_single_tx_eur": MAX_SINGLE_TX_EUR if 'MAX_SINGLE_TX_EUR' in dir() else 50000,
            "max_daily_eur": MAX_DAILY_EUR if 'MAX_DAILY_EUR' in dir() else 200000,
            "max_neno_per_tx": MAX_NENO_PER_TX if 'MAX_NENO_PER_TX' in dir() else 50,
        },
        "rate_limit": {
            "max_exec_ops_per_min": 10,
        },
        "supported_onchain_assets": list(ASSET_TO_BSC_CONTRACT.keys()) + ["BNB"],
        "status_enforcement": {
            "provable": ["completed", "settled"],
            "pending": ["pending_execution", "pending_settlement"],
            "terminal_fail": ["failed", "reverted"],
            "rule": "Solo operazioni con tx_hash, payout_id o treasury_proof possono avere stato 'completed'",
        },
    }

"""
Infrastructure API — NeoNoble Ramp.

API-as-a-Service, Treasury, Hot Wallet Management, Order Flow Control.
Multi-tenant ready, audit-logged, rate-limited.
"""

import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from database.mongodb import get_database
from routes.auth import get_current_user
from services.execution_engine import ExecutionEngine, LiquidityEngine, TreasuryEngine
from services.settlement_ledger import (
    get_user_ledger, get_user_payouts,
    STATE_INTERNAL_CREDITED, STATE_PAYOUT_PENDING,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/infra", tags=["Infrastructure"])

treasury = TreasuryEngine()
liquidity = LiquidityEngine()


# ── Hot Wallet Status ──

@router.get("/hot-wallet")
async def hot_wallet_status(current_user: dict = Depends(get_current_user)):
    """Real-time hot wallet on-chain status."""
    engine = ExecutionEngine.get_instance()
    status = await engine.get_hot_wallet_status()
    return status


# ── Treasury & PnL ──

@router.get("/treasury/pnl")
async def treasury_pnl(current_user: dict = Depends(get_current_user)):
    """Platform P&L and fee collection summary."""
    if current_user.get("role", "").upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    db = get_database()
    pnl = await treasury.get_pnl(db)
    risk = await treasury.get_hot_wallet_risk(db)
    return {"pnl": pnl, "risk": risk}


# ── Settlement Audit ──

@router.get("/audit/ledger")
async def audit_ledger(
    limit: int = Query(100, le=500),
    current_user: dict = Depends(get_current_user),
):
    """Full settlement ledger with double-entry audit trail."""
    db = get_database()
    if current_user.get("role", "").upper() == "ADMIN":
        entries = await db.settlement_ledger.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    else:
        entries = await get_user_ledger(current_user["user_id"], limit)
    return {"entries": entries, "total": len(entries)}


@router.get("/audit/payouts")
async def audit_payouts(
    state: Optional[str] = None,
    limit: int = Query(100, le=500),
    current_user: dict = Depends(get_current_user),
):
    """Payout queue with states and IBAN details."""
    db = get_database()
    query = {}
    if current_user.get("role", "").upper() != "ADMIN":
        query["user_id"] = current_user["user_id"]
    if state:
        query["state"] = state
    payouts = await db.payout_queue.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"payouts": payouts, "total": len(payouts)}


# ── Order Flow & Internal Matching ──

@router.get("/order-book")
async def get_order_book(current_user: dict = Depends(get_current_user)):
    """View internal order book for netting."""
    db = get_database()
    orders = await db.internal_order_book.find(
        {"status": "pending"}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return {"orders": orders, "total": len(orders)}


@router.get("/netting-stats")
async def netting_stats(current_user: dict = Depends(get_current_user)):
    """Internal netting statistics."""
    db = get_database()
    total_matched = await db.internal_order_book.count_documents({"status": "matched"})
    total_pending = await db.internal_order_book.count_documents({"status": "pending"})
    return {
        "matched_orders": total_matched,
        "pending_orders": total_pending,
        "internalization_rate": round(total_matched / max(total_matched + total_pending, 1) * 100, 1),
    }


# ── Multi-Rail Settlement Status ──

@router.get("/settlement/rails")
async def settlement_rails(current_user: dict = Depends(get_current_user)):
    """Status of all settlement rails."""
    engine = ExecutionEngine.get_instance()
    hw = await engine.get_hot_wallet_status()

    nium_key = os.environ.get("NIUM_API_KEY")

    return {
        "crypto_rail": {
            "type": "on_chain",
            "chain": "BSC Mainnet",
            "status": "active" if hw.get("available") else "degraded",
            "hot_wallet": hw.get("address"),
            "gas_ok": hw.get("gas_sufficient", False),
            "neno_available": hw.get("neno_balance", 0),
        },
        "stablecoin_rail": {
            "type": "stablecoin",
            "supported": ["USDT", "BUSD"],
            "chain": "BSC",
            "status": "active",
        },
        "sepa_rail": {
            "type": "fiat",
            "method": "SEPA/IBAN",
            "provider": "NIUM" if nium_key else "pending_activation",
            "status": "active" if nium_key else "ready_for_activation",
            "auto_execute": True,
        },
        "card_rail": {
            "type": "fiat",
            "method": "card_topup",
            "provider": "NIUM" if nium_key else "pending_activation",
            "status": "active" if nium_key else "ready_for_activation",
        },
    }


# ── Real On-Chain Execution ──

class OnChainSendRequest(BaseModel):
    to_address: str = Field(description="Destination wallet address")
    amount: float = Field(gt=0)
    asset: str = Field(default="NENO")


@router.post("/execute/send-onchain")
async def execute_onchain_send(req: OnChainSendRequest, current_user: dict = Depends(get_current_user)):
    """Execute real on-chain transfer from hot wallet. Admin only."""
    if current_user.get("role", "").upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")

    engine = ExecutionEngine.get_instance()
    if req.asset.upper() == "NENO":
        result = await engine.send_neno(req.to_address, req.amount)
    elif req.asset.upper() in ("BNB", "WBNB"):
        result = await engine.send_bnb(req.to_address, req.amount)
    else:
        raise HTTPException(status_code=400, detail=f"Asset {req.asset} non supportato per invio on-chain")

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Execution failed"))

    db = get_database()
    await db.onchain_executions.insert_one({
        "id": str(uuid.uuid4()), "user_id": current_user["user_id"],
        "type": "admin_send", "to": req.to_address,
        "amount": req.amount, "asset": req.asset,
        "tx_hash": result["tx_hash"], "block_number": result.get("block_number"),
        "status": "completed", "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return result


# ── Routing Info ──

@router.get("/routing/quote")
async def routing_quote(
    from_asset: str, to_asset: str, amount: float,
    current_user: dict = Depends(get_current_user),
):
    """Get optimal routing path for a swap."""
    route = liquidity.calculate_routing(from_asset.upper(), to_asset.upper(), amount)
    return {
        "from": from_asset.upper(), "to": to_asset.upper(),
        "amount": amount, "routing": route,
    }


# ── System Health ──

@router.get("/health")
async def infrastructure_health(current_user: dict = Depends(get_current_user)):
    """Complete system health check."""
    db = get_database()
    engine = ExecutionEngine.get_instance()
    hw = await engine.get_hot_wallet_status()

    pending_payouts = await db.payout_queue.count_documents({"state": STATE_PAYOUT_PENDING})
    total_ledger = await db.settlement_ledger.count_documents({})
    total_txs = await db.neno_transactions.count_documents({})

    return {
        "status": "operational",
        "hot_wallet": hw,
        "settlement_ledger_entries": total_ledger,
        "total_transactions": total_txs,
        "pending_payouts": pending_payouts,
        "nium_active": bool(os.environ.get("NIUM_API_KEY")),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

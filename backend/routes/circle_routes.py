"""
Circle USDC API Routes — NeoNoble Ramp.

REST endpoints for Circle USDC Programmable Wallets:
- Wallet balances (on-chain verified)
- Wallet segregation status
- Transfer operations
- Reconciliation
- Auto-operation loop control
- Full audit trail
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from routes.auth import get_current_user
from services.circle_wallet_service import CircleWalletService, WalletRole, SEGREGATED_WALLETS
from services.wallet_segregation_engine import WalletSegregationEngine
from services.auto_operation_loop import AutoOperationLoop

router = APIRouter(prefix="/circle", tags=["Circle USDC"])


# ── Models ──

class TransferRequest(BaseModel):
    from_wallet: str = Field(..., description="Source wallet role: client, treasury, revenue")
    to_address: str = Field(..., description="Destination address")
    amount: str = Field(..., description="Amount USDC")


class SegregationMoveRequest(BaseModel):
    from_role: str
    to_role: str
    amount_usdc: float
    reason: str = "manual_rebalance"


# ── WALLET BALANCES ──

@router.get("/wallets/balances")
async def get_wallet_balances(
    chain: str = "BSC",
    current_user: dict = Depends(get_current_user),
):
    """Get real on-chain USDC balances for all 3 segregated wallets."""
    circle = CircleWalletService.get_instance()
    balances = await circle.get_all_wallet_balances(chain)
    return balances


@router.get("/wallets/{role}/balance")
async def get_single_wallet_balance(
    role: str,
    chain: str = "BSC",
    current_user: dict = Depends(get_current_user),
):
    """Get real USDC balance for a specific wallet role."""
    if role not in SEGREGATED_WALLETS:
        raise HTTPException(status_code=400, detail=f"Ruolo non valido: {role}. Usa: client, treasury, revenue")
    circle = CircleWalletService.get_instance()
    address = SEGREGATED_WALLETS[role]
    balance = await circle.get_onchain_usdc_balance(address, chain)
    return {"role": role, "address": address, **balance}


# ── SEGREGATION STATUS ──

@router.get("/segregation/summary")
async def segregation_summary(current_user: dict = Depends(get_current_user)):
    """Get wallet segregation summary with movement statistics."""
    engine = WalletSegregationEngine.get_instance()
    return await engine.get_summary()


@router.get("/segregation/movements")
async def segregation_movements(
    limit: int = 50,
    wallet: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Get recent wallet segregation movements."""
    engine = WalletSegregationEngine.get_instance()
    movements = await engine.get_movements(limit=limit, wallet_role=wallet)
    return {"movements": movements, "count": len(movements)}


@router.get("/segregation/reconciliation")
async def segregation_reconciliation(current_user: dict = Depends(get_current_user)):
    """Reconcile on-chain balances vs ledger movements."""
    engine = WalletSegregationEngine.get_instance()
    return await engine.reconcile()


@router.post("/segregation/move")
async def manual_segregation_move(
    req: SegregationMoveRequest,
    current_user: dict = Depends(get_current_user),
):
    """Admin: manually move funds between segregated wallets (audit-logged)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Solo admin puo fare movimenti manuali")

    valid_roles = {WalletRole.CLIENT, WalletRole.TREASURY, WalletRole.REVENUE}
    if req.from_role not in valid_roles or req.to_role not in valid_roles:
        raise HTTPException(status_code=400, detail="Ruoli validi: client, treasury, revenue")

    engine = WalletSegregationEngine.get_instance()
    result = await engine.record_movement(
        from_role=req.from_role,
        to_role=req.to_role,
        amount_usdc=req.amount_usdc,
        rule_type="admin_rebalance",
        metadata={"reason": req.reason, "admin": current_user.get("email", "")},
    )
    return result


# ── CIRCLE API OPERATIONS ──

@router.get("/diagnostic")
async def circle_diagnostic(current_user: dict = Depends(get_current_user)):
    """Full Circle integration health check."""
    circle = CircleWalletService.get_instance()
    return await circle.get_diagnostic()


@router.post("/wallets/create")
async def create_circle_wallet(current_user: dict = Depends(get_current_user)):
    """Create a new Circle programmable wallet (admin only)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    circle = CircleWalletService.get_instance()
    if not circle.is_active:
        raise HTTPException(status_code=503, detail="Circle service non attivo")
    result = await circle.create_wallet()
    await circle.log_operation("create_wallet", result)
    return result


@router.post("/transfer")
async def transfer_usdc(
    req: TransferRequest,
    current_user: dict = Depends(get_current_user),
):
    """Transfer USDC from a Circle wallet (admin only, audit-logged)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")

    circle = CircleWalletService.get_instance()
    if not circle.is_active:
        raise HTTPException(status_code=503, detail="Circle service non attivo")

    # Validate amount
    try:
        float(req.amount)
    except ValueError:
        raise HTTPException(status_code=400, detail="Importo non valido")

    # Log operation
    await circle.log_operation("transfer_request", {
        "from_wallet": req.from_wallet,
        "to_address": req.to_address,
        "amount": req.amount,
        "requested_by": current_user.get("email", ""),
    })

    return {
        "status": "transfer_logged",
        "note": "Transfer reale richiede wallet_id Circle. Usa l'API Circle direttamente per invio on-chain.",
        "from_wallet": req.from_wallet,
        "to_address": req.to_address,
        "amount": req.amount,
    }


# ── AUTO-OPERATION LOOP ──

@router.get("/auto-op/status")
async def auto_op_status(current_user: dict = Depends(get_current_user)):
    """Get auto-operation loop status."""
    loop = AutoOperationLoop.get_instance()
    return await loop.get_status()


@router.post("/auto-op/start")
async def auto_op_start(current_user: dict = Depends(get_current_user)):
    """Start the autonomous operation loop (admin only)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    loop = AutoOperationLoop.get_instance()
    await loop.start()
    return {"status": "started", "message": "Loop autonomo avviato"}


@router.post("/auto-op/stop")
async def auto_op_stop(current_user: dict = Depends(get_current_user)):
    """Stop the autonomous operation loop (admin only)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    loop = AutoOperationLoop.get_instance()
    await loop.stop()
    return {"status": "stopped", "message": "Loop autonomo fermato"}


# ── FAIL-SAFE REPORT ──

@router.get("/fail-safe/report")
async def fail_safe_report(current_user: dict = Depends(get_current_user)):
    """
    Fail-safe reality check report.
    Shows what is blocked and why.
    """
    from database.mongodb import get_database
    db = get_database()

    circle = CircleWalletService.get_instance()
    balances = await circle.get_all_wallet_balances("BSC")

    # Count blocked operations
    blocked = await db.auto_op_events.count_documents({"event": "operation_blocked"})
    total_ops = await db.auto_op_metrics.count_documents({})

    return {
        "fail_safe_active": True,
        "rules": {
            "no_simulation": True,
            "no_artificial_funds": True,
            "no_uncovered_operations": True,
            "real_execution_only": True,
        },
        "current_state": {
            "total_usdc_onchain": balances.get("total_usdc", 0),
            "client_wallet": balances["wallets"].get(WalletRole.CLIENT, {}).get("balance", 0),
            "treasury_wallet": balances["wallets"].get(WalletRole.TREASURY, {}).get("balance", 0),
            "revenue_wallet": balances["wallets"].get(WalletRole.REVENUE, {}).get("balance", 0),
        },
        "statistics": {
            "total_cycles": total_ops,
            "blocked_operations": blocked,
        },
        "verified_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }

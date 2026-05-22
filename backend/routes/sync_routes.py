"""
Real-Time Sync API Routes — NeoNoble Ramp.

Unified endpoints for real-time state across all platform systems:
- Wallet balances (on-chain + ledger + Circle)
- Exchange state (fills, PnL)
- Cashout pipeline
- Instant withdraw status
"""

from fastapi import APIRouter, Depends
from routes.auth import get_current_user
from services.realtime_sync_service import RealtimeSyncService
from services.instant_withdraw_engine import InstantWithdrawEngine

router = APIRouter(prefix="/sync", tags=["Real-Time Sync"])


@router.get("/state")
async def get_realtime_state(current_user: dict = Depends(get_current_user)):
    """
    Full real-time platform state.
    Single endpoint for complete visibility across ALL systems.
    Every call reads REAL data (no cache).
    """
    sync = RealtimeSyncService.get_instance()
    return await sync.get_full_state(user_id=current_user.get("user_id"))


@router.get("/state/platform")
async def get_platform_state(current_user: dict = Depends(get_current_user)):
    """Platform-wide state (no user-specific data)."""
    sync = RealtimeSyncService.get_instance()
    return await sync.get_full_state()


@router.get("/instant-withdraw/status")
async def instant_withdraw_status(current_user: dict = Depends(get_current_user)):
    """Instant withdraw engine status and history."""
    engine = InstantWithdrawEngine.get_instance()
    return await engine.get_status()


@router.get("/reconciliation")
async def sync_reconciliation(current_user: dict = Depends(get_current_user)):
    """Real-time reconciliation: on-chain vs ledger vs cashout pipeline."""
    from services.wallet_segregation_engine import WalletSegregationEngine
    from services.circle_wallet_service import CircleWalletService, WalletRole
    from database.mongodb import get_database
    import asyncio

    seg = WalletSegregationEngine.get_instance()
    circle = CircleWalletService.get_instance()
    db = get_database()

    recon, usdc, pending_cashouts = await asyncio.gather(
        seg.reconcile(),
        circle.get_all_wallet_balances("BSC"),
        db.cashout_log.count_documents({"status": "pending_execution"}),
    )

    return {
        "reconciliation": recon,
        "usdc_verified": usdc.get("total_usdc", 0),
        "pending_cashouts": pending_cashouts,
        "system_healthy": recon["status"] == "clean",
    }

"""
Live Execution API Routes — NeoNoble Ramp.

Endpoints for real money activation:
- Pipeline assessment (readiness check)
- Pipeline execution (Swap → Convert → Settle → Withdraw)
- DEX swap quotes and execution
- Swap history
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from routes.auth import get_current_user
from services.dex_swap_service import DexSwapService, NENO_CONTRACT, USDC_BSC, WBNB
from services.live_pipeline import LivePipeline

router = APIRouter(prefix="/live", tags=["Live Execution"])


class SwapRequest(BaseModel):
    from_token: str = Field(default="NENO", description="Source asset")
    to_token: str = Field(default="USDC", description="Destination asset")
    amount: float = Field(..., description="Amount to swap")


# Token address mapping
TOKEN_MAP = {
    "NENO": NENO_CONTRACT,
    "WBNB": WBNB,
    "USDC": USDC_BSC,
    "USDT": "0x55d398326f99059fF775485246999027B3197955",
    "BUSD": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
}


# ── PIPELINE ──

@router.get("/pipeline/assess")
async def assess_pipeline(current_user: dict = Depends(get_current_user)):
    """
    Assess pipeline readiness: liquidity, quotes, balances, fiat rails, blockers.
    Does NOT execute — read-only assessment.
    """
    pipeline = LivePipeline.get_instance()
    return await pipeline.assess_pipeline()


@router.post("/pipeline/execute")
async def execute_pipeline(current_user: dict = Depends(get_current_user)):
    """
    Execute full pipeline: Swap → Convert → Settle → Withdraw.
    Admin only. Returns stage-by-stage results with TX hashes.
    """
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    pipeline = LivePipeline.get_instance()
    return await pipeline.execute_full_pipeline()


# ── DEX QUOTES ──

@router.get("/dex/quote")
async def dex_quote(
    from_asset: str = "NENO",
    to_asset: str = "USDC",
    amount: float = 1.0,
    current_user: dict = Depends(get_current_user),
):
    """Get real PancakeSwap V2 swap quote."""
    dex = DexSwapService.get_instance()

    from_addr = TOKEN_MAP.get(from_asset.upper())
    to_addr = TOKEN_MAP.get(to_asset.upper())

    if not from_addr or not to_addr:
        raise HTTPException(status_code=400, detail=f"Asset sconosciuto: {from_asset} o {to_asset}")

    quote = await dex.get_swap_quote(from_addr, to_addr, amount)
    return quote


@router.get("/dex/liquidity/{asset}")
async def check_liquidity(
    asset: str,
    current_user: dict = Depends(get_current_user),
):
    """Check DEX liquidity for an asset."""
    dex = DexSwapService.get_instance()
    token_addr = TOKEN_MAP.get(asset.upper())
    if not token_addr:
        raise HTTPException(status_code=400, detail=f"Asset sconosciuto: {asset}")
    return await dex.check_liquidity(token_addr, WBNB)


# ── DEX EXECUTION ──

@router.post("/dex/swap")
async def execute_dex_swap(
    req: SwapRequest,
    current_user: dict = Depends(get_current_user),
):
    """Execute real on-chain DEX swap (admin only)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")

    dex = DexSwapService.get_instance()
    from_addr = TOKEN_MAP.get(req.from_token.upper())
    to_addr = TOKEN_MAP.get(req.to_token.upper())

    if not from_addr or not to_addr:
        raise HTTPException(status_code=400, detail="Asset sconosciuto")

    if req.from_token.upper() == "BNB":
        return await dex.execute_bnb_to_usdc(req.amount)

    return await dex.execute_swap(from_addr, to_addr, req.amount)


@router.post("/dex/convert-neno")
async def convert_neno(
    amount: float = None,
    current_user: dict = Depends(get_current_user),
):
    """Convert NENO → USDC via PancakeSwap (admin only)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")

    dex = DexSwapService.get_instance()
    if amount is None:
        from services.execution_engine import ExecutionEngine
        engine = ExecutionEngine.get_instance()
        status = await engine.get_hot_wallet_status()
        amount = status.get("neno_balance", 0)

    if amount <= 0:
        raise HTTPException(status_code=400, detail="No NENO available")

    return await dex.convert_neno_to_usdc(amount)


# ── HISTORY ──

@router.get("/dex/history")
async def swap_history(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """DEX swap execution history."""
    dex = DexSwapService.get_instance()
    history = await dex.get_swap_history(limit)
    return {"swaps": history, "count": len(history)}


@router.get("/pipeline/history")
async def pipeline_history(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Pipeline execution history."""
    from database.mongodb import get_database
    db = get_database()
    history = await db.pipeline_executions.find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return {"pipelines": history, "count": len(history)}

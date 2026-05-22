from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from decimal import Decimal
from typing import Optional

from backend.engines.swap_engine import SwapEngine, SwapRequest

router = APIRouter(prefix="/api/swap", tags=["Swap"])

swap_engine = SwapEngine()

class SwapRequestAPI(BaseModel):
    user_id: str
    from_token: str
    to_token: str
    amount_in: Decimal
    chain: str = "bsc"
    slippage: float = 0.8
    user_wallet_address: str   # Indirizzo del wallet che deve ricevere i token


class SwapResponse(BaseModel):
    success: bool
    tx_hash: Optional[str] = None
    amount_out: Optional[Decimal] = None
    error: Optional[str] = None


@router.post("/", response_model=SwapResponse)
async def perform_swap(request: SwapRequestAPI):
    try:
        # Converti la request API nella request interna dell'engine
        engine_request = SwapRequest(
            user_id=request.user_id,
            from_token=request.from_token,
            to_token=request.to_token,
            amount_in=request.amount_in,
            chain=request.chain,
            slippage=request.slippage,
            user_wallet_address=request.user_wallet_address
        )

        result = await swap_engine.execute_swap(engine_request)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Swap failed: {str(e)}")


@router.get("/quote")
async def get_swap_quote(from_token: str, to_token: str, amount_in: Decimal, chain: str = "bsc"):
    # Placeholder per il calcolo della quote (da espandere)
    estimated_out = amount_in * Decimal("0.95")
    return {
        "from_token": from_token,
        "to_token": to_token,
        "amount_in": amount_in,
        "estimated_amount_out": estimated_out,
        "chain": chain
    }

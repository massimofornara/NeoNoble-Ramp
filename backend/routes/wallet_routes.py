"""
Wallet & Settlement API Routes.

Provides endpoints for:
- User wallet management (multi-asset)
- Asset conversion (crypto↔crypto, crypto↔fiat)
- Settlement pipeline
- Card funding from crypto
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional

from database.mongodb import get_database
from routes.auth import get_current_user
from services.settlement_engine import (
    convert_assets, fund_card_from_crypto, settle_trade,
    get_user_wallets, get_settlement_history, get_conversion_rate,
    CONVERSION_RATES
)

router = APIRouter(prefix="/wallet", tags=["Wallet & Settlement"])


class ConvertRequest(BaseModel):
    from_asset: str
    to_asset: str
    amount: float = Field(gt=0)


class FundCardRequest(BaseModel):
    card_id: str
    crypto_asset: str
    crypto_amount: float = Field(gt=0)


class DepositRequest(BaseModel):
    asset: str
    amount: float = Field(gt=0)


@router.get("/balances")
async def get_wallets(current_user: dict = Depends(get_current_user)):
    """Get all wallet balances for the current user."""
    wallets = await get_user_wallets(current_user["user_id"])
    total_eur = sum(w.get("eur_value", 0) for w in wallets)
    return {"wallets": wallets, "total_eur_value": round(total_eur, 2)}


@router.post("/deposit")
async def deposit_to_wallet(request: DepositRequest, current_user: dict = Depends(get_current_user)):
    """Deposit assets to wallet (simulated for platform testing)."""
    db = get_database()
    asset = request.asset.upper()
    await db.wallets.update_one(
        {"user_id": current_user["user_id"], "asset": asset},
        {
            "$inc": {"balance": request.amount},
            "$setOnInsert": {"user_id": current_user["user_id"], "asset": asset},
        },
        upsert=True,
    )
    wallet = await db.wallets.find_one(
        {"user_id": current_user["user_id"], "asset": asset}, {"_id": 0}
    )
    return {"message": f"Deposited {request.amount} {asset}", "balance": round(wallet.get("balance", 0), 8)}


@router.post("/convert")
async def convert(request: ConvertRequest, current_user: dict = Depends(get_current_user)):
    """Convert between any supported assets. Crypto↔Crypto, Crypto↔Fiat, Fiat↔Crypto."""
    try:
        result = await convert_assets(
            user_id=current_user["user_id"],
            from_asset=request.from_asset,
            to_asset=request.to_asset,
            amount=request.amount,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/fund-card")
async def fund_card(request: FundCardRequest, current_user: dict = Depends(get_current_user)):
    """Fund a card from crypto balance. Pipeline: Crypto → Conversion → Fiat → Card."""
    try:
        result = await fund_card_from_crypto(
            user_id=current_user["user_id"],
            card_id=request.card_id,
            crypto_asset=request.crypto_asset,
            crypto_amount=request.crypto_amount,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/settlements")
async def get_settlements(
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user)
):
    """Get settlement history."""
    settlements = await get_settlement_history(current_user["user_id"], limit)
    return {"settlements": settlements, "total": len(settlements)}


@router.get("/conversion-rates")
async def get_rates():
    """Get available conversion rates."""
    rates = {}
    for asset, targets in CONVERSION_RATES.items():
        rates[asset] = {k: v for k, v in targets.items()}
    return {"rates": rates, "supported_assets": list(CONVERSION_RATES.keys())}

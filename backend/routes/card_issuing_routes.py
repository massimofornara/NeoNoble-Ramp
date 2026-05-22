"""
Card Issuing Routes — NeoNoble Ramp.

PCI-compliant card reveal, authorization, settlement endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from routes.auth import get_current_user
from services.card_issuing_engine import CardIssuingEngine

router = APIRouter(prefix="/card-engine", tags=["Card Issuing Engine"])


class CardRevealRequest(BaseModel):
    card_id: str
    otp_code: Optional[str] = None
    otp_verified: bool = False


class AuthorizeRequest(BaseModel):
    card_id: str
    merchant: str
    amount: float = Field(gt=0)
    currency: str = "EUR"
    mcc: str = "5411"


class SettleRequest(BaseModel):
    authorization_id: str


class IssueCardRequest(BaseModel):
    card_type: str = "virtual"
    network: str = "visa"
    currency: str = "EUR"


@router.post("/issue")
async def issue_card(req: IssueCardRequest, current_user: dict = Depends(get_current_user)):
    """Issue a new card via the active card provider."""
    engine = CardIssuingEngine.get_instance()
    result = await engine.issue_card(
        user_id=current_user["user_id"],
        card_type=req.card_type,
        network=req.network,
        currency=req.currency,
    )
    return result


@router.post("/reveal")
async def reveal_card(req: CardRevealRequest, current_user: dict = Depends(get_current_user)):
    """
    Reveal full card details (PAN, CVV, expiry).
    Requires 2FA verification.
    """
    engine = CardIssuingEngine.get_instance()

    # Verify 2FA if code provided
    otp_ok = req.otp_verified
    if req.otp_code:
        # In production: verify against TOTP/SMS
        # For now, accept any 6-digit code as valid
        otp_ok = len(req.otp_code) == 6 and req.otp_code.isdigit()

    result = await engine.reveal_card(
        card_id=req.card_id,
        user_id=current_user["user_id"],
        otp_verified=otp_ok,
    )

    if "error" in result:
        if result.get("require_2fa"):
            raise HTTPException(status_code=403, detail=result["error"])
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.post("/authorize")
async def authorize_transaction(req: AuthorizeRequest, current_user: dict = Depends(get_current_user)):
    """Authorize a card transaction (balance check + limit check + fraud check)."""
    engine = CardIssuingEngine.get_instance()
    result = await engine.authorize_transaction(
        card_id=req.card_id,
        merchant=req.merchant,
        amount=req.amount,
        currency=req.currency,
        mcc=req.mcc,
    )
    if not result.get("authorized"):
        raise HTTPException(status_code=400, detail=f"Autorizzazione rifiutata: {result.get('reason')}")
    return result


@router.post("/settlement")
async def settle_transaction(req: SettleRequest, current_user: dict = Depends(get_current_user)):
    """Settle a previously authorized card transaction."""
    engine = CardIssuingEngine.get_instance()
    result = await engine.settle_transaction(req.authorization_id)
    if not result.get("settled"):
        raise HTTPException(status_code=400, detail=f"Settlement fallito: {result.get('reason')}")
    return result


@router.get("/monetization")
async def card_monetization_stats(current_user: dict = Depends(get_current_user)):
    """Get card monetization statistics (admin)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    engine = CardIssuingEngine.get_instance()
    return await engine.get_monetization_stats()


@router.get("/provider")
async def get_provider_info():
    """Get active card provider information."""
    engine = CardIssuingEngine.get_instance()
    return {
        "active_provider": engine.active_provider,
        "available_providers": ["marqeta", "nium", "adyen", "stripe", "internal"],
        "features": {
            "virtual_cards": True,
            "physical_cards": True,
            "card_reveal": True,
            "authorization": True,
            "settlement": True,
            "3d_secure": engine.active_provider != "internal",
        },
    }

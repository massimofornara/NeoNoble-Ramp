"""
Crypto Card Infrastructure API Routes.

Provides endpoints for:
- Virtual and physical card management
- Card issuance and activation
- Transaction history
- Crypto-to-fiat conversion for card spending

Note: Actual card issuance requires integration with a licensed card issuer
(Visa/Mastercard partner). This module provides the platform infrastructure
ready for issuer integration.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from enum import Enum
import uuid

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/cards", tags=["Card Infrastructure"])


class CardType(str, Enum):
    VIRTUAL = "virtual"
    PHYSICAL = "physical"


class CardStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    FROZEN = "frozen"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class CardNetwork(str, Enum):
    VISA = "visa"
    MASTERCARD = "mastercard"


class CreateCardRequest(BaseModel):
    card_type: CardType
    card_network: CardNetwork = CardNetwork.VISA
    currency: str = Field(default="EUR", description="Fiat currency for the card")
    funding_source: str = Field(default="platform_balance", description="Crypto asset to fund card")
    daily_limit: float = Field(default=1000.0, ge=0)
    monthly_limit: float = Field(default=10000.0, ge=0)
    shipping_address: Optional[dict] = Field(None, description="Required for physical cards")


class TopUpCardRequest(BaseModel):
    amount_crypto: float = Field(gt=0)
    crypto_asset: str = Field(default="BTC")


class FreezeCardRequest(BaseModel):
    reason: Optional[str] = None


CARD_FEES = {
    "virtual": {"issuance": 0.0, "monthly": 0.0},
    "physical": {"issuance": 9.99, "monthly": 1.99, "delivery": 14.99},
}


@router.post("/create")
async def create_card(request: CreateCardRequest, current_user: dict = Depends(get_current_user)):
    """Request a new virtual or physical card."""
    db = get_database()

    existing = await db.cards.count_documents({
        "user_id": current_user["user_id"],
        "status": {"$in": ["pending", "active"]},
        "card_type": request.card_type
    })
    if existing >= 3:
        raise HTTPException(status_code=400, detail=f"Maximum 3 {request.card_type} cards allowed")

    if request.card_type == "physical" and not request.shipping_address:
        raise HTTPException(status_code=400, detail="Indirizzo di spedizione richiesto per carta fisica")

    card_number_masked = f"**** **** **** {uuid.uuid4().hex[:4].upper()}"
    fees = CARD_FEES[request.card_type]

    card = {
        "id": str(uuid.uuid4()),
        "user_id": current_user["user_id"],
        "card_type": request.card_type,
        "card_network": request.card_network,
        "card_number_masked": card_number_masked,
        "currency": request.currency,
        "funding_source": request.funding_source,
        "balance": 0.0,
        "daily_limit": request.daily_limit,
        "monthly_limit": request.monthly_limit,
        "daily_spent": 0.0,
        "monthly_spent": 0.0,
        "status": "active" if request.card_type == "virtual" else "pending_shipment",
        "issuance_fee": fees["issuance"],
        "monthly_fee": fees.get("monthly", 0),
        "issuer": "NIUM",
        "funding_sources": ["fiat", "crypto", "neno"],
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1095),
    }

    if request.card_type == "physical":
        card["shipping_address"] = request.shipping_address
        card["shipping_status"] = "processing"
        card["tracking_number"] = f"NN-{uuid.uuid4().hex[:10].upper()}"
        card["estimated_delivery"] = "5-10 giorni lavorativi"
        card["delivery_fee"] = fees.get("delivery", 14.99)

    await db.cards.insert_one({**card, "_id": card["id"]})

    # Serialize datetimes for response
    card_resp = {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in card.items()}
    return {
        "message": f"{'Carta virtuale attivata' if request.card_type == 'virtual' else 'Carta fisica in lavorazione'}",
        "card": card_resp
    }


@router.get("/my-cards")
async def get_my_cards(current_user: dict = Depends(get_current_user)):
    """Get all cards for current user."""
    db = get_database()
    cards = await db.cards.find(
        {"user_id": current_user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(20)

    for c in cards:
        if "created_at" in c and hasattr(c["created_at"], "isoformat"):
            c["created_at"] = c["created_at"].isoformat()
        if "expires_at" in c and hasattr(c["expires_at"], "isoformat"):
            c["expires_at"] = c["expires_at"].isoformat()

    return {"cards": cards, "total": len(cards)}


@router.post("/{card_id}/top-up")
async def top_up_card(card_id: str, request: TopUpCardRequest, current_user: dict = Depends(get_current_user)):
    """Top up card balance with crypto conversion."""
    db = get_database()
    card = await db.cards.find_one({"id": card_id, "user_id": current_user["user_id"]})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if card["status"] != "active":
        raise HTTPException(status_code=400, detail="Card is not active")

    conversion_rates = {
        "BTC": 60787.0, "ETH": 1769.0, "NENO": 10000.0,
        "USDT": 0.92, "SOL": 74.72, "BNB": 555.36,
    }
    rate = conversion_rates.get(request.crypto_asset.upper(), 1.0)
    fiat_amount = round(request.amount_crypto * rate, 2)

    await db.cards.update_one(
        {"id": card_id},
        {"$inc": {"balance": fiat_amount}}
    )

    tx = {
        "id": str(uuid.uuid4()),
        "card_id": card_id,
        "user_id": current_user["user_id"],
        "type": "top_up",
        "crypto_asset": request.crypto_asset.upper(),
        "crypto_amount": request.amount_crypto,
        "fiat_amount": fiat_amount,
        "currency": card["currency"],
        "conversion_rate": rate,
        "status": "completed",
        "created_at": datetime.now(timezone.utc),
    }
    await db.card_transactions.insert_one({**tx, "_id": tx["id"]})

    return {
        "message": f"Top-up di €{fiat_amount} completato",
        "transaction": {k: v for k, v in tx.items() if k != "_id"},
        "new_balance": round((card.get("balance", 0) + fiat_amount), 2)
    }


@router.post("/{card_id}/freeze")
async def freeze_card(card_id: str, request: FreezeCardRequest, current_user: dict = Depends(get_current_user)):
    """Freeze/unfreeze a card."""
    db = get_database()
    card = await db.cards.find_one({"id": card_id, "user_id": current_user["user_id"]})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    new_status = "frozen" if card["status"] == "active" else "active"
    await db.cards.update_one({"id": card_id}, {"$set": {"status": new_status}})

    return {"message": f"Carta {'congelata' if new_status == 'frozen' else 'riattivata'}", "status": new_status}


@router.post("/{card_id}/cancel")
async def cancel_card(card_id: str, current_user: dict = Depends(get_current_user)):
    """Cancel a card permanently."""
    db = get_database()
    card = await db.cards.find_one({"id": card_id, "user_id": current_user["user_id"]})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if card["status"] == "cancelled":
        raise HTTPException(status_code=400, detail="Card already cancelled")

    await db.cards.update_one({"id": card_id}, {"$set": {"status": "cancelled"}})
    return {"message": "Carta cancellata permanentemente"}


@router.get("/{card_id}/shipping")
async def get_shipping_status(card_id: str, current_user: dict = Depends(get_current_user)):
    """Get shipping status for a physical card."""
    db = get_database()
    card = await db.cards.find_one({"id": card_id, "user_id": current_user["user_id"]})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if card.get("card_type") != "physical":
        raise HTTPException(status_code=400, detail="Solo le carte fisiche hanno tracking spedizione")

    return {
        "card_id": card_id,
        "shipping_status": card.get("shipping_status", "unknown"),
        "tracking_number": card.get("tracking_number"),
        "estimated_delivery": card.get("estimated_delivery"),
        "shipping_address": card.get("shipping_address"),
    }




@router.get("/{card_id}/transactions")
async def get_card_transactions(
    card_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Get transaction history for a card."""
    db = get_database()
    card = await db.cards.find_one({"id": card_id, "user_id": current_user["user_id"]})
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    skip = (page - 1) * page_size
    total = await db.card_transactions.count_documents({"card_id": card_id})
    txns = await db.card_transactions.find(
        {"card_id": card_id}, {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)

    for t in txns:
        if "created_at" in t and hasattr(t["created_at"], "isoformat"):
            t["created_at"] = t["created_at"].isoformat()

    return {"transactions": txns, "total": total, "page": page}


@router.get("/admin/overview")
async def admin_card_overview(current_user: dict = Depends(get_current_user)):
    """Admin overview of card infrastructure."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")

    db = get_database()

    total = await db.cards.count_documents({})
    active = await db.cards.count_documents({"status": "active"})
    virtual = await db.cards.count_documents({"card_type": "virtual"})
    physical = await db.cards.count_documents({"card_type": "physical"})
    frozen = await db.cards.count_documents({"status": "frozen"})

    pipeline = [
        {"$match": {"type": "top_up", "status": "completed"}},
        {"$group": {"_id": None, "total_volume": {"$sum": "$fiat_amount"}, "count": {"$sum": 1}}}
    ]
    topup_stats = await db.card_transactions.aggregate(pipeline).to_list(1)
    topup = topup_stats[0] if topup_stats else {"total_volume": 0, "count": 0}

    return {
        "cards": {"total": total, "active": active, "virtual": virtual, "physical": physical, "frozen": frozen},
        "transactions": {"total_top_ups": topup.get("count", 0), "total_volume": topup.get("total_volume", 0)},
    }

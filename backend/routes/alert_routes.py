"""
Price Alert & Browser Push Routes.

Endpoints:
- POST /alerts/create — Create price alert
- GET  /alerts — List user's alerts
- DELETE /alerts/{id} — Delete alert
- GET /browser-push/pending — Poll for browser push notifications
- POST /browser-push/delivered — Mark push as delivered
- POST /alerts/check — Background trigger to check all alerts (admin)
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional
import uuid

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(tags=["Alerts & Push"])


# ── Models ──

class CreateAlertRequest(BaseModel):
    asset: str = Field(description="BTC, ETH, NENO, etc.")
    condition: str = Field(description="above or below")
    threshold: float = Field(description="Price threshold in EUR")
    note: Optional[str] = None


# ── Price Alerts ──

@router.post("/alerts/create")
async def create_price_alert(req: CreateAlertRequest, current_user: dict = Depends(get_current_user)):
    """Create a price alert for an asset."""
    db = get_database()
    uid = current_user["user_id"]

    # Max 20 alerts per user
    count = await db.price_alerts.count_documents({"user_id": uid, "triggered": False})
    if count >= 20:
        raise HTTPException(status_code=400, detail="Massimo 20 alert attivi")

    if req.condition not in ("above", "below"):
        raise HTTPException(status_code=400, detail="Condizione deve essere 'above' o 'below'")

    alert = {
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "asset": req.asset.upper(),
        "condition": req.condition,
        "threshold": req.threshold,
        "note": req.note,
        "triggered": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.price_alerts.insert_one({**alert, "_id": alert["id"]})
    return {"message": "Alert creato", "alert": alert}


@router.get("/alerts")
async def get_alerts(current_user: dict = Depends(get_current_user)):
    """Get user's price alerts."""
    db = get_database()
    alerts = await db.price_alerts.find(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    active = sum(1 for a in alerts if not a.get("triggered"))
    return {"alerts": alerts, "active_count": active}


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a price alert."""
    db = get_database()
    result = await db.price_alerts.delete_one({"id": alert_id, "user_id": current_user["user_id"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Alert non trovato")
    return {"message": "Alert eliminato"}


@router.post("/alerts/check")
async def check_all_alerts():
    """Check all active price alerts against current prices (background task)."""
    from services.notification_dispatch import notify_price_alert

    db = get_database()
    # Get current prices
    PRICES = {
        "BTC": 60787.0, "ETH": 1769.0, "BNB": 555.36, "NENO": 10000.0,
        "SOL": 74.72, "XRP": 1.21, "ADA": 0.38, "DOGE": 0.082,
        "AVAX": 24.50, "DOT": 5.12, "LINK": 13.80, "UNI": 8.45,
        "MATIC": 0.55, "USDT": 0.92, "USDC": 0.92,
    }

    # Try dynamic NENO price
    try:
        from routes.neno_exchange_routes import _get_dynamic_neno_price
        pricing = await _get_dynamic_neno_price()
        PRICES["NENO"] = pricing["price"]
    except Exception:
        pass

    triggered_count = 0
    active_alerts = await db.price_alerts.find({"triggered": False}, {"_id": 0}).to_list(500)

    for alert in active_alerts:
        asset = alert.get("asset", "")
        current_price = PRICES.get(asset)
        if current_price is None:
            continue

        condition = alert.get("condition")
        threshold = alert.get("threshold", 0)
        should_trigger = False

        if condition == "above" and current_price >= threshold:
            should_trigger = True
        elif condition == "below" and current_price <= threshold:
            should_trigger = True

        if should_trigger:
            await db.price_alerts.update_one(
                {"id": alert["id"]},
                {"$set": {"triggered": True, "triggered_at": datetime.now(timezone.utc).isoformat(), "triggered_price": current_price}},
            )
            await notify_price_alert(alert["user_id"], asset, current_price, condition, threshold)
            triggered_count += 1

    return {"checked": len(active_alerts), "triggered": triggered_count}


# ── Browser Push Polling ──

@router.get("/browser-push/pending")
async def get_pending_push(current_user: dict = Depends(get_current_user)):
    """Poll for pending browser push notifications."""
    db = get_database()
    pending = await db.browser_push_queue.find(
        {"user_id": current_user["user_id"], "delivered": False}, {"_id": 0}
    ).sort("created_at", -1).limit(10).to_list(10)
    return {"notifications": pending}


@router.post("/browser-push/delivered")
async def mark_push_delivered(current_user: dict = Depends(get_current_user)):
    """Mark all pending pushes as delivered."""
    db = get_database()
    result = await db.browser_push_queue.update_many(
        {"user_id": current_user["user_id"], "delivered": False},
        {"$set": {"delivered": True, "delivered_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"marked": result.modified_count}

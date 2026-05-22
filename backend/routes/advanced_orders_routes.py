"""
Advanced Orders — Limit, Stop, Trailing Stop.

Extends the trading engine with:
- Limit orders: Execute at or better than specified price
- Stop orders: Trigger market order when price hits stop level
- Trailing stop: Dynamic stop that follows price movement
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/trading/orders", tags=["Advanced Orders"])


class LimitOrderRequest(BaseModel):
    pair_id: str
    side: str = Field(description="buy or sell")
    quantity: float = Field(gt=0)
    limit_price: float = Field(gt=0)
    time_in_force: str = Field(default="GTC", description="GTC, IOC, FOK")


class StopOrderRequest(BaseModel):
    pair_id: str
    side: str = Field(description="buy or sell")
    quantity: float = Field(gt=0)
    stop_price: float = Field(gt=0)
    limit_price: Optional[float] = None


class TrailingStopRequest(BaseModel):
    pair_id: str
    side: str = Field(description="buy or sell")
    quantity: float = Field(gt=0)
    trail_amount: Optional[float] = None
    trail_percent: Optional[float] = None


class CancelOrderRequest(BaseModel):
    order_id: str


@router.post("/limit")
async def place_limit_order(req: LimitOrderRequest, current_user: dict = Depends(get_current_user)):
    """Place a limit order."""
    db = get_database()
    uid = current_user["user_id"]

    order = {
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "type": "limit",
        "pair_id": req.pair_id,
        "side": req.side,
        "quantity": req.quantity,
        "limit_price": req.limit_price,
        "time_in_force": req.time_in_force,
        "filled_qty": 0,
        "avg_fill_price": 0,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Reserve funds
    pair = await db.trading_engine_pairs.find_one({"id": req.pair_id}, {"_id": 0})
    if not pair:
        raise HTTPException(status_code=404, detail="Coppia non trovata")

    if req.side == "buy":
        required = req.quantity * req.limit_price
        quote_asset = req.pair_id.split("-")[1] if "-" in req.pair_id else "EUR"
        wallet = await db.wallets.find_one({"user_id": uid, "asset": quote_asset})
        if not wallet or wallet.get("balance", 0) < required:
            raise HTTPException(status_code=400, detail=f"Saldo {quote_asset} insufficiente")
        await db.wallets.update_one({"user_id": uid, "asset": quote_asset}, {"$inc": {"balance": -required}})
        order["reserved_amount"] = required
        order["reserved_asset"] = quote_asset
    else:
        base_asset = req.pair_id.split("-")[0] if "-" in req.pair_id else req.pair_id
        wallet = await db.wallets.find_one({"user_id": uid, "asset": base_asset})
        if not wallet or wallet.get("balance", 0) < req.quantity:
            raise HTTPException(status_code=400, detail=f"Saldo {base_asset} insufficiente")
        await db.wallets.update_one({"user_id": uid, "asset": base_asset}, {"$inc": {"balance": -req.quantity}})
        order["reserved_amount"] = req.quantity
        order["reserved_asset"] = base_asset

    await db.advanced_orders.insert_one({**order, "_id": order["id"]})

    return {"message": f"Ordine limit {req.side} piazzato a {req.limit_price}", "order": order}


@router.post("/stop")
async def place_stop_order(req: StopOrderRequest, current_user: dict = Depends(get_current_user)):
    """Place a stop or stop-limit order."""
    db = get_database()
    uid = current_user["user_id"]

    order = {
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "type": "stop" if req.limit_price is None else "stop_limit",
        "pair_id": req.pair_id,
        "side": req.side,
        "quantity": req.quantity,
        "stop_price": req.stop_price,
        "limit_price": req.limit_price,
        "filled_qty": 0,
        "avg_fill_price": 0,
        "triggered": False,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.advanced_orders.insert_one({**order, "_id": order["id"]})
    return {"message": f"Ordine stop {req.side} a {req.stop_price}", "order": order}


@router.post("/trailing-stop")
async def place_trailing_stop(req: TrailingStopRequest, current_user: dict = Depends(get_current_user)):
    """Place a trailing stop order."""
    db = get_database()
    uid = current_user["user_id"]

    if not req.trail_amount and not req.trail_percent:
        raise HTTPException(status_code=400, detail="Specifica trail_amount o trail_percent")

    # Get current price
    pair = await db.trading_engine_pairs.find_one({"id": req.pair_id}, {"_id": 0})
    current_price = pair.get("last_price", 0) if pair else 0

    if req.trail_percent:
        trail_distance = current_price * (req.trail_percent / 100)
    else:
        trail_distance = req.trail_amount

    if req.side == "sell":
        activation_price = current_price - trail_distance
    else:
        activation_price = current_price + trail_distance

    order = {
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "type": "trailing_stop",
        "pair_id": req.pair_id,
        "side": req.side,
        "quantity": req.quantity,
        "trail_amount": trail_distance,
        "trail_percent": req.trail_percent,
        "current_stop": activation_price,
        "highest_price": current_price if req.side == "sell" else None,
        "lowest_price": current_price if req.side == "buy" else None,
        "triggered": False,
        "status": "tracking",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.advanced_orders.insert_one({**order, "_id": order["id"]})
    return {"message": f"Trailing stop impostato con distanza {trail_distance}", "order": order}


@router.get("/active")
async def get_active_orders(current_user: dict = Depends(get_current_user)):
    """Get all active orders for current user."""
    db = get_database()
    orders = await db.advanced_orders.find(
        {"user_id": current_user["user_id"], "status": {"$in": ["open", "pending", "tracking"]}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)
    return {"orders": orders, "total": len(orders)}


@router.get("/history")
async def get_order_history(current_user: dict = Depends(get_current_user)):
    """Get order history."""
    db = get_database()
    orders = await db.advanced_orders.find(
        {"user_id": current_user["user_id"]},
        {"_id": 0},
    ).sort("created_at", -1).to_list(200)
    return {"orders": orders, "total": len(orders)}


@router.post("/cancel")
async def cancel_order(req: CancelOrderRequest, current_user: dict = Depends(get_current_user)):
    """Cancel an active order and return reserved funds."""
    db = get_database()
    order = await db.advanced_orders.find_one(
        {"id": req.order_id, "user_id": current_user["user_id"]}, {"_id": 0}
    )
    if not order:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    if order["status"] in ("filled", "cancelled"):
        raise HTTPException(status_code=400, detail="Ordine gia' completato o cancellato")

    # Return reserved funds
    if order.get("reserved_amount") and order.get("reserved_asset"):
        unfilled = order["reserved_amount"] * ((order["quantity"] - order.get("filled_qty", 0)) / order["quantity"])
        if unfilled > 0:
            await db.wallets.update_one(
                {"user_id": current_user["user_id"], "asset": order["reserved_asset"]},
                {"$inc": {"balance": unfilled}},
            )

    await db.advanced_orders.update_one(
        {"id": req.order_id},
        {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}},
    )

    return {"message": "Ordine cancellato", "order_id": req.order_id}

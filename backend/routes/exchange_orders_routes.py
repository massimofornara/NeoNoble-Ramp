"""
Exchange Orders API — Matching Engine + Order Book + Smart Router.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone

from database.mongodb import get_database
from routes.auth import get_current_user
from services.matching_engine import MatchingEngine, OrderType, OrderSide
from services.risk_engine import RiskEngine
from services.smart_router import SmartRouter
from services.clearing_engine import ClearingEngine
from services.profit_engine import ProfitEngine

router = APIRouter(prefix="/exchange-orders", tags=["Exchange Orders"])


class SubmitOrderRequest(BaseModel):
    pair: str = Field(description="Trading pair (e.g. NENO/EUR)")
    side: str = Field(description="buy or sell")
    order_type: str = Field(default="market", description="market or limit")
    quantity: float = Field(gt=0)
    price: Optional[float] = Field(None, description="Limit price (required for limit orders)")
    destination_wallet: Optional[str] = None


@router.post("/submit")
async def submit_order(req: SubmitOrderRequest, current_user: dict = Depends(get_current_user)):
    uid = current_user["user_id"]
    engine = MatchingEngine.get_instance()

    if req.order_type == OrderType.LIMIT and req.price is None:
        raise HTTPException(status_code=400, detail="Prezzo richiesto per ordini limit")

    risk = RiskEngine.get_instance()
    base_asset = req.pair.split("/")[0] if "/" in req.pair else req.pair
    price_check = req.price or 10000
    risk_check = await risk.pre_trade_check(uid, base_asset, req.quantity, price_check, req.side)
    if not risk_check["approved"]:
        failed = [c for c in risk_check["checks"] if not c["pass"]]
        raise HTTPException(status_code=400, detail=f"Risk check fallito: {failed[0]['detail']}" if failed else "Risk check fallito")

    order = await engine.submit_order(
        user_id=uid, pair=req.pair, side=req.side,
        order_type=req.order_type, quantity=req.quantity,
        price=req.price, destination_wallet=req.destination_wallet,
    )

    if order.get("fills"):
        profit = ProfitEngine.get_instance()
        for fill in order["fills"]:
            await profit.record_fee(
                tx_id=fill["fill_id"],
                fee_amount=round(fill["quantity"] * fill["price"] * 0.003, 4),
                fee_asset="EUR", tx_type="order_fill", user_id=uid,
            )

    return {"order": order, "risk_check": risk_check}


@router.post("/cancel/{order_id}")
async def cancel_order(order_id: str, current_user: dict = Depends(get_current_user)):
    engine = MatchingEngine.get_instance()
    result = await engine.cancel_order(order_id, current_user["user_id"])
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/book/{pair}")
async def get_order_book(pair: str, depth: int = 20):
    engine = MatchingEngine.get_instance()
    return engine.get_order_book_snapshot(pair, depth)


@router.get("/fills/{pair}")
async def get_fills(pair: str, limit: int = 50):
    engine = MatchingEngine.get_instance()
    return {"fills": await engine.get_recent_fills(pair, limit)}


@router.get("/my-orders")
async def get_my_orders(current_user: dict = Depends(get_current_user)):
    db = get_database()
    orders = await db.orders.find(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    for o in orders:
        if isinstance(o.get("created_at"), datetime):
            o["created_at"] = o["created_at"].isoformat()
        if isinstance(o.get("updated_at"), datetime):
            o["updated_at"] = o["updated_at"].isoformat()
    return {"orders": orders}


@router.get("/route/{asset}")
async def get_best_route(asset: str, side: str = "buy", amount: float = 1.0):
    router_svc = SmartRouter.get_instance()
    return await router_svc.find_best_route(asset, side, amount)

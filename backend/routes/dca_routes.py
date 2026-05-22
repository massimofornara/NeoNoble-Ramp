"""
DCA (Dollar-Cost Averaging) Trading Bot Routes.

Automated recurring purchases of crypto at configured intervals.
Plans execute via the background scheduler.

Endpoints:
- POST /create     — Create a new DCA plan
- GET  /plans      — List user's DCA plans
- POST /pause      — Pause a plan
- POST /resume     — Resume a paused plan
- DELETE /plans/{id} — Cancel a plan
- GET  /history    — Get execution history for a plan
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/dca", tags=["DCA Bot"])

VALID_INTERVALS = ["hourly", "daily", "weekly", "biweekly", "monthly"]
VALID_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "NENO", "AVAX", "DOT", "LINK"]

REF_PRICES = {
    "BTC": 60787.0, "ETH": 1769.0, "SOL": 74.72, "BNB": 555.36,
    "XRP": 1.21, "ADA": 0.38, "DOGE": 0.082, "NENO": 10000.0,
    "AVAX": 24.50, "DOT": 5.12, "LINK": 13.80,
}


class CreateDCAPlanRequest(BaseModel):
    asset: str = Field(description="Target crypto asset")
    amount_eur: float = Field(gt=0, description="EUR amount per execution")
    interval: str = Field(default="daily", description="hourly, daily, weekly, biweekly, monthly")
    max_executions: Optional[int] = Field(None, ge=1, description="Max executions (null=unlimited)")


class PausePlanRequest(BaseModel):
    plan_id: str


@router.post("/create")
async def create_dca_plan(req: CreateDCAPlanRequest, current_user: dict = Depends(get_current_user)):
    """Create a new DCA plan."""
    if req.asset.upper() not in VALID_ASSETS:
        raise HTTPException(status_code=400, detail=f"Asset non supportato. Disponibili: {', '.join(VALID_ASSETS)}")
    if req.interval not in VALID_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Intervallo non valido. Disponibili: {', '.join(VALID_INTERVALS)}")

    db = get_database()
    uid = current_user["user_id"]

    # Check EUR balance
    wallet = await db.wallets.find_one({"user_id": uid, "asset": "EUR"})
    eur_balance = wallet.get("balance", 0) if wallet else 0
    if eur_balance < req.amount_eur:
        raise HTTPException(status_code=400, detail=f"Saldo EUR insufficiente: {eur_balance:.2f}")

    plan = {
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "asset": req.asset.upper(),
        "amount_eur": req.amount_eur,
        "interval": req.interval,
        "max_executions": req.max_executions,
        "total_executions": 0,
        "total_invested_eur": 0.0,
        "total_acquired": 0.0,
        "avg_price": 0.0,
        "status": "active",
        "next_execution": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.dca_plans.insert_one({**plan, "_id": plan["id"]})
    return {"message": f"Piano DCA creato: {req.amount_eur} EUR → {req.asset} ogni {req.interval}", "plan": plan}


@router.get("/plans")
async def get_dca_plans(current_user: dict = Depends(get_current_user)):
    """List user's DCA plans."""
    db = get_database()
    plans = await db.dca_plans.find(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {"plans": plans, "total": len(plans)}


@router.post("/pause")
async def pause_dca_plan(req: PausePlanRequest, current_user: dict = Depends(get_current_user)):
    """Pause an active DCA plan."""
    db = get_database()
    result = await db.dca_plans.update_one(
        {"id": req.plan_id, "user_id": current_user["user_id"], "status": "active"},
        {"$set": {"status": "paused"}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Piano non trovato o non attivo")
    return {"message": "Piano DCA in pausa"}


@router.post("/resume")
async def resume_dca_plan(req: PausePlanRequest, current_user: dict = Depends(get_current_user)):
    """Resume a paused DCA plan."""
    db = get_database()
    result = await db.dca_plans.update_one(
        {"id": req.plan_id, "user_id": current_user["user_id"], "status": "paused"},
        {"$set": {"status": "active", "next_execution": datetime.now(timezone.utc).isoformat()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Piano non trovato o non in pausa")
    return {"message": "Piano DCA ripreso"}


@router.delete("/plans/{plan_id}")
async def cancel_dca_plan(plan_id: str, current_user: dict = Depends(get_current_user)):
    """Cancel (delete) a DCA plan."""
    db = get_database()
    result = await db.dca_plans.update_one(
        {"id": plan_id, "user_id": current_user["user_id"]},
        {"$set": {"status": "cancelled"}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Piano non trovato")
    return {"message": "Piano DCA cancellato"}


@router.get("/history")
async def get_dca_history(
    plan_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Get DCA execution history."""
    db = get_database()
    query = {"user_id": current_user["user_id"]}
    if plan_id:
        query["plan_id"] = plan_id
    execs = await db.dca_executions.find(query, {"_id": 0}).sort("executed_at", -1).to_list(limit)
    return {"executions": execs, "total": len(execs)}


async def execute_dca_plans():
    """Called by the background scheduler. Executes all due DCA plans."""
    from database.mongodb import get_database
    db = get_database()
    now = datetime.now(timezone.utc)

    active_plans = await db.dca_plans.find({"status": "active"}).to_list(500)
    executed = 0

    for plan in active_plans:
        next_exec = plan.get("next_execution", "")
        if isinstance(next_exec, str) and next_exec:
            next_dt = datetime.fromisoformat(next_exec.replace("Z", "+00:00")) if "+" not in next_exec and next_exec.endswith("Z") else datetime.fromisoformat(next_exec) if isinstance(next_exec, str) else next_exec
        elif isinstance(next_exec, datetime):
            next_dt = next_exec
        else:
            continue

        if next_dt.tzinfo is None:
            next_dt = next_dt.replace(tzinfo=timezone.utc)

        if now < next_dt:
            continue

        # Check max executions
        if plan.get("max_executions") and plan.get("total_executions", 0) >= plan["max_executions"]:
            await db.dca_plans.update_one({"id": plan["id"]}, {"$set": {"status": "completed"}})
            continue

        # Check EUR balance
        wallet = await db.wallets.find_one({"user_id": plan["user_id"], "asset": "EUR"})
        eur_balance = wallet.get("balance", 0) if wallet else 0
        if eur_balance < plan["amount_eur"]:
            await db.dca_plans.update_one(
                {"id": plan["id"]},
                {"$set": {"status": "paused", "pause_reason": "Saldo EUR insufficiente"}}
            )
            continue

        # Execute the purchase
        asset = plan["asset"]
        price = REF_PRICES.get(asset, 0)
        if price <= 0:
            continue

        amount_eur = plan["amount_eur"]
        qty = round(amount_eur / price, 8)
        fee = round(amount_eur * 0.003, 2)

        # Deduct EUR, credit asset
        await db.wallets.update_one({"user_id": plan["user_id"], "asset": "EUR"}, {"$inc": {"balance": -amount_eur}})
        await db.wallets.update_one(
            {"user_id": plan["user_id"], "asset": asset},
            {"$inc": {"balance": qty}, "$setOnInsert": {"user_id": plan["user_id"], "asset": asset}},
            upsert=True,
        )

        # Record execution
        execution = {
            "id": str(uuid.uuid4()),
            "plan_id": plan["id"],
            "user_id": plan["user_id"],
            "asset": asset,
            "amount_eur": amount_eur,
            "quantity": qty,
            "price": price,
            "fee": fee,
            "executed_at": now.isoformat(),
        }
        await db.dca_executions.insert_one({**execution, "_id": execution["id"]})

        # Calculate next execution
        interval_map = {"hourly": 3600, "daily": 86400, "weekly": 604800, "biweekly": 1209600, "monthly": 2592000}
        next_secs = interval_map.get(plan["interval"], 86400)
        from datetime import timedelta
        next_run = now + timedelta(seconds=next_secs)

        new_total_invested = (plan.get("total_invested_eur", 0) + amount_eur)
        new_total_acquired = (plan.get("total_acquired", 0) + qty)
        new_avg = new_total_invested / new_total_acquired if new_total_acquired > 0 else 0

        await db.dca_plans.update_one(
            {"id": plan["id"]},
            {"$inc": {"total_executions": 1, "total_invested_eur": amount_eur, "total_acquired": qty},
             "$set": {"avg_price": round(new_avg, 4), "next_execution": next_run.isoformat(), "last_execution": now.isoformat()}},
        )
        executed += 1

    return executed

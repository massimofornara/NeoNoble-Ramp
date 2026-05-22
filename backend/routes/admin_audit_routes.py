"""
Admin Audit Log Viewer — Platform-wide audit trail for administrators.

Provides:
- Browse all platform events (trades, KYC, logins, withdrawals)
- Filter by user, event type, date range
- Export audit data as CSV
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone, timedelta
from typing import Optional
import io
import csv

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/admin/audit", tags=["Admin Audit"])


async def _require_admin(current_user: dict = Depends(get_current_user)):
    db = get_database()
    user = await db.users.find_one({"id": current_user["user_id"]}, {"_id": 0})
    if not user or user.get("role", "").upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Accesso riservato agli amministratori")
    return current_user


@router.get("/logs")
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200),
    event_type: Optional[str] = None,
    user_email: Optional[str] = None,
    severity: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: dict = Depends(_require_admin),
):
    """Get paginated audit logs with filters."""
    db = get_database()
    query = {}

    if event_type:
        query["type"] = event_type
    if severity:
        query["severity"] = severity

    if user_email:
        user = await db.users.find_one({"email": user_email}, {"_id": 0, "id": 1})
        if user:
            query["user_id"] = user["id"]
        else:
            return {"logs": [], "total": 0, "page": page, "page_size": page_size}

    if date_from:
        query.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        query.setdefault("created_at", {})["$lte"] = date_to

    # Search across multiple audit collections
    logs = []

    # 1. Notifications (system events)
    notifs = await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).skip((page - 1) * page_size).limit(page_size).to_list(page_size)
    for n in notifs:
        n["source"] = "notification"
    logs.extend(notifs)

    # 2. NENO transactions
    neno_query = {}
    if user_email and "user_id" in query:
        neno_query["user_id"] = query["user_id"]
    neno_txs = await db.neno_transactions.find(neno_query, {"_id": 0}).sort("created_at", -1).limit(page_size).to_list(page_size)
    for t in neno_txs:
        t["source"] = "neno_exchange"
        if hasattr(t.get("created_at"), "isoformat"):
            t["created_at"] = t["created_at"].isoformat()
    logs.extend(neno_txs)

    # 3. Banking transactions
    bank_query = {}
    if "user_id" in query:
        bank_query["user_id"] = query["user_id"]
    bank_txs = await db.banking_transactions.find(bank_query, {"_id": 0}).sort("created_at", -1).limit(page_size).to_list(page_size)
    for t in bank_txs:
        t["source"] = "banking"
        if hasattr(t.get("created_at"), "isoformat"):
            t["created_at"] = t["created_at"].isoformat()
    logs.extend(bank_txs)

    # 4. KYC activity
    kyc_query = {}
    if "user_id" in query:
        kyc_query["user_id"] = query["user_id"]
    kyc_records = await db.kyc_profiles.find(kyc_query, {"_id": 0}).sort("updated_at", -1).limit(page_size).to_list(page_size)
    for k in kyc_records:
        k["source"] = "kyc"
        if hasattr(k.get("updated_at"), "isoformat"):
            k["created_at"] = k["updated_at"].isoformat()
    logs.extend(kyc_records)

    # Sort combined by created_at desc
    logs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    logs = logs[:page_size]

    total = await db.notifications.count_documents({}) + await db.neno_transactions.count_documents({})
    return {"logs": logs, "total": total, "page": page, "page_size": page_size}


@router.get("/stats")
async def get_audit_stats(current_user: dict = Depends(_require_admin)):
    """Get audit statistics for the admin dashboard."""
    db = get_database()
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    stats = {
        "total_users": await db.users.count_documents({}),
        "total_neno_transactions": await db.neno_transactions.count_documents({}),
        "total_banking_transactions": await db.banking_transactions.count_documents({}),
        "total_notifications": await db.notifications.count_documents({}),
        "kyc_pending": await db.kyc_profiles.count_documents({"status": "pending_review"}),
        "kyc_approved": await db.kyc_profiles.count_documents({"status": {"$in": ["verified", "approved"]}}),
        "neno_txs_24h": await db.neno_transactions.count_documents({"created_at": {"$gte": day_ago}}),
        "bank_txs_7d": await db.banking_transactions.count_documents({"created_at": {"$gte": week_ago}}),
        "active_margin_positions": await db.margin_positions.count_documents({"status": "open"}),
        "total_cards_issued": await db.cards.count_documents({}),
        "aml_alerts": await db.aml_alerts.count_documents({"status": "open"}),
    }
    return stats


@router.get("/export/csv")
async def export_audit_csv(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(_require_admin),
):
    """Export audit logs as CSV file."""
    db = get_database()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "source", "type", "user_id", "amount", "status", "details"])

    # NENO transactions
    async for tx in db.neno_transactions.find({"created_at": {"$gte": cutoff}}, {"_id": 0}).sort("created_at", -1):
        ts = tx.get("created_at", "")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        writer.writerow([
            ts, "neno_exchange", tx.get("type", ""),
            tx.get("user_id", ""), tx.get("neno_amount", ""),
            tx.get("status", ""), tx.get("pay_asset", tx.get("receive_asset", "")),
        ])

    # Banking
    async for tx in db.banking_transactions.find({"created_at": {"$gte": cutoff}}, {"_id": 0}).sort("created_at", -1):
        ts = tx.get("created_at", "")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        writer.writerow([
            ts, "banking", tx.get("type", ""),
            tx.get("user_id", ""), tx.get("amount", ""),
            tx.get("status", ""), tx.get("reference", ""),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit_export_{days}d.csv"},
    )

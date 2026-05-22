"""
Analytics API Routes.

Provides endpoints for:
- Page view tracking
- User engagement metrics
- Admin analytics dashboard data
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])


class PageViewEvent(BaseModel):
    page: str
    referrer: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/track")
async def track_page_view(event: PageViewEvent, request: Request):
    """Track a page view. No auth required for tracking."""
    db = get_database()
    await db.analytics_events.insert_one({
        "type": "page_view",
        "page": event.page,
        "referrer": event.referrer,
        "session_id": event.session_id,
        "ip": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", ""),
        "created_at": datetime.now(timezone.utc)
    })
    return {"status": "ok"}


@router.get("/admin/overview")
async def admin_analytics_overview(
    days: int = Query(30, ge=1, le=365),
    current_user: dict = Depends(get_current_user)
):
    """Get analytics overview for admin dashboard."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")

    db = get_database()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    pipeline_views = [
        {"$match": {"type": "page_view", "created_at": {"$gte": since}}},
        {"$group": {"_id": "$page", "views": {"$sum": 1}}},
        {"$sort": {"views": -1}}
    ]
    page_views = await db.analytics_events.aggregate(pipeline_views).to_list(50)

    pipeline_daily = [
        {"$match": {"type": "page_view", "created_at": {"$gte": since}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "views": {"$sum": 1},
            "unique_sessions": {"$addToSet": "$session_id"}
        }},
        {"$sort": {"_id": 1}}
    ]
    daily_stats = await db.analytics_events.aggregate(pipeline_daily).to_list(365)

    total_views = sum(p["views"] for p in page_views)
    total_unique = len(set())

    daily_data = []
    for d in daily_stats:
        sessions = [s for s in d.get("unique_sessions", []) if s]
        daily_data.append({
            "date": d["_id"],
            "views": d["views"],
            "unique_visitors": len(sessions)
        })

    total_users = await db.users.count_documents({})
    active_users = await db.users.count_documents({"last_login": {"$gte": since}})
    new_users = await db.users.count_documents({"created_at": {"$gte": since}})

    total_tokens = await db.tokens.count_documents({})
    total_subs = await db.subscriptions.count_documents({"status": "active"})
    total_listings = await db.token_listings.count_documents({})

    return {
        "period_days": days,
        "page_views": {
            "total": total_views,
            "by_page": [{"page": p["_id"], "views": p["views"]} for p in page_views],
        },
        "daily_traffic": daily_data,
        "users": {
            "total": total_users,
            "active": active_users,
            "new": new_users,
        },
        "platform": {
            "tokens": total_tokens,
            "active_subscriptions": total_subs,
            "listings": total_listings,
        },
        "updated_at": datetime.now(timezone.utc).isoformat()
    }


@router.get("/admin/engagement")
async def admin_engagement_metrics(
    days: int = Query(7, ge=1, le=90),
    current_user: dict = Depends(get_current_user)
):
    """Get user engagement metrics."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")

    db = get_database()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    pipeline_sessions = [
        {"$match": {"type": "page_view", "created_at": {"$gte": since}, "session_id": {"$ne": None}}},
        {"$group": {
            "_id": "$session_id",
            "pages": {"$sum": 1},
            "first_view": {"$min": "$created_at"},
            "last_view": {"$max": "$created_at"},
        }},
    ]
    sessions = await db.analytics_events.aggregate(pipeline_sessions).to_list(10000)

    avg_pages = sum(s["pages"] for s in sessions) / max(len(sessions), 1)
    avg_duration_sec = 0
    if sessions:
        durations = [(s["last_view"] - s["first_view"]).total_seconds() for s in sessions if s["pages"] > 1]
        avg_duration_sec = sum(durations) / max(len(durations), 1)

    recent_tokens = await db.tokens.count_documents({"created_at": {"$gte": since}})
    recent_subs = await db.subscriptions.count_documents({"created_at": {"$gte": since}})
    recent_listings = await db.token_listings.count_documents({"created_at": {"$gte": since}})

    return {
        "period_days": days,
        "sessions": len(sessions),
        "avg_pages_per_session": round(avg_pages, 1),
        "avg_session_duration_seconds": round(avg_duration_sec),
        "recent_activity": {
            "tokens_created": recent_tokens,
            "subscriptions": recent_subs,
            "listings": recent_listings,
        }
    }

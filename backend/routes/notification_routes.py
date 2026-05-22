"""
Push Notifications Service.

Server-side notification system with:
- In-app notifications (stored in DB, fetched by frontend)
- Notification types: trade, margin, kyc, security, system
- Read/unread tracking
- Real-time delivery via SSE (Server-Sent Events)
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid
import asyncio
import json

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationCreate(BaseModel):
    title: str
    message: str
    type: str = Field(default="system", description="trade, margin, kyc, security, system")
    severity: str = Field(default="info", description="info, warning, critical")
    action_url: Optional[str] = None


# ── SSE subscribers ──
_sse_queues: dict = {}  # user_id -> asyncio.Queue


async def push_notification(user_id: str, title: str, message: str, notif_type: str = "system", severity: str = "info", action_url: str = None):
    """Create and push a notification to a user."""
    db = get_database()
    notif = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notif_type,
        "severity": severity,
        "action_url": action_url,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.notifications.insert_one({**notif, "_id": notif["id"]})

    # Push to SSE if connected
    if user_id in _sse_queues:
        try:
            _sse_queues[user_id].put_nowait(notif)
        except asyncio.QueueFull:
            pass

    return notif


@router.get("/")
async def get_notifications(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Get notifications for current user."""
    db = get_database()
    query = {"user_id": current_user["user_id"]}
    if unread_only:
        query["read"] = False

    notifs = await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    unread = await db.notifications.count_documents({"user_id": current_user["user_id"], "read": False})

    return {"notifications": notifs, "unread_count": unread, "total": len(notifs)}


@router.post("/read/{notification_id}")
async def mark_as_read(notification_id: str, current_user: dict = Depends(get_current_user)):
    """Mark a notification as read."""
    db = get_database()
    result = await db.notifications.update_one(
        {"id": notification_id, "user_id": current_user["user_id"]},
        {"$set": {"read": True}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notifica non trovata")
    return {"message": "Notifica letta"}


@router.post("/read-all")
async def mark_all_as_read(current_user: dict = Depends(get_current_user)):
    """Mark all notifications as read."""
    db = get_database()
    result = await db.notifications.update_many(
        {"user_id": current_user["user_id"], "read": False},
        {"$set": {"read": True}},
    )
    return {"message": f"{result.modified_count} notifiche lette"}


@router.delete("/{notification_id}")
async def delete_notification(notification_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a notification."""
    db = get_database()
    await db.notifications.delete_one({"id": notification_id, "user_id": current_user["user_id"]})
    return {"message": "Notifica eliminata"}


@router.get("/stream")
async def notification_stream(request: Request, current_user: dict = Depends(get_current_user)):
    """SSE endpoint for real-time notifications."""
    user_id = current_user["user_id"]
    queue = asyncio.Queue(maxsize=50)
    _sse_queues[user_id] = queue

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    notif = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(notif)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        finally:
            _sse_queues.pop(user_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.get("/unread-count")
async def get_unread_count(current_user: dict = Depends(get_current_user)):
    """Get unread notification count."""
    db = get_database()
    count = await db.notifications.count_documents({"user_id": current_user["user_id"], "read": False})
    return {"unread_count": count}

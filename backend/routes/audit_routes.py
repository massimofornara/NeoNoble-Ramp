"""
Audit Routes - Transaction Audit Log API.

Provides endpoints for:
- Session management
- Event logging
- Timeline visualization
- Compliance export
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime, timezone

from services.audit_service import (
    TransactionAuditService,
    AuditEventType,
    get_audit_service
)

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit", tags=["Audit"])


# Request/Response Models

class CreateSessionRequest(BaseModel):
    """Request to create audit session."""
    user_id: Optional[str] = None
    product_type: str = Field(..., description="BUY or SELL")
    order_id: Optional[str] = None
    metadata: Optional[Dict] = None


class LogEventRequest(BaseModel):
    """Request to log an audit event."""
    session_id: str
    event_type: str
    description: str = ""
    order_id: Optional[str] = None
    transak_order_id: Optional[str] = None
    metadata: Optional[Dict] = None


class CloseSessionRequest(BaseModel):
    """Request to close audit session."""
    session_id: str
    status: str = "completed"
    summary: Optional[Dict] = None


# Dependency

def get_service() -> TransactionAuditService:
    service = get_audit_service()
    if not service:
        raise HTTPException(status_code=503, detail="Audit service not available")
    return service


# Routes

@router.post("/sessions")
async def create_session(
    request: CreateSessionRequest,
    req: Request,
    service: TransactionAuditService = Depends(get_service)
):
    """Create a new audit session."""
    metadata = request.metadata or {}
    metadata["client_ip"] = req.client.host if req.client else None
    metadata["user_agent"] = req.headers.get("user-agent")
    
    session = await service.create_session(
        user_id=request.user_id,
        product_type=request.product_type,
        order_id=request.order_id,
        metadata=metadata
    )
    
    return {
        "session_id": session.session_id,
        "status": session.status,
        "started_at": session.started_at
    }


@router.post("/events")
async def log_event(
    request: LogEventRequest,
    req: Request,
    service: TransactionAuditService = Depends(get_service)
):
    """Log an audit event."""
    try:
        event_type = AuditEventType(request.event_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event_type. Valid types: {[e.value for e in AuditEventType]}"
        )
    
    event = await service.log_event(
        session_id=request.session_id,
        event_type=event_type,
        description=request.description,
        order_id=request.order_id,
        transak_order_id=request.transak_order_id,
        metadata=request.metadata,
        ip_address=req.client.host if req.client else None,
        user_agent=req.headers.get("user-agent")
    )
    
    return {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp
    }


@router.post("/sessions/close")
async def close_session(
    request: CloseSessionRequest,
    service: TransactionAuditService = Depends(get_service)
):
    """Close an audit session."""
    await service.close_session(
        session_id=request.session_id,
        status=request.status,
        summary=request.summary
    )
    
    return {"status": "closed", "session_id": request.session_id}


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    service: TransactionAuditService = Depends(get_service)
):
    """Get session with all events."""
    session = await service.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session


@router.get("/sessions/by-order/{order_id}")
async def get_session_by_order(
    order_id: str,
    service: TransactionAuditService = Depends(get_service)
):
    """Get session by order ID."""
    session = await service.get_session_by_order(order_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found for order")
    
    return session


@router.get("/timeline/{session_id}")
async def get_timeline(
    session_id: str,
    service: TransactionAuditService = Depends(get_service)
):
    """Get visual timeline data for a session."""
    timeline = await service.get_timeline(session_id)
    
    if "error" in timeline:
        raise HTTPException(status_code=404, detail=timeline["error"])
    
    return timeline


@router.get("/users/{user_id}/sessions")
async def get_user_sessions(
    user_id: str,
    limit: int = Query(20, le=100),
    skip: int = 0,
    service: TransactionAuditService = Depends(get_service)
):
    """Get all sessions for a user."""
    sessions = await service.get_user_sessions(
        user_id=user_id,
        limit=limit,
        skip=skip
    )
    
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/export/{session_id}")
async def export_session_report(
    session_id: str,
    service: TransactionAuditService = Depends(get_service)
):
    """Export session as compliance report."""
    report = await service.export_session_report(session_id)
    
    if "error" in report:
        raise HTTPException(status_code=404, detail=report["error"])
    
    return report


@router.get("/event-types")
async def get_event_types():
    """Get all available event types."""
    return {
        "event_types": [
            {
                "value": e.value,
                "name": e.name,
                "category": _get_event_category(e)
            }
            for e in AuditEventType
        ]
    }


def _get_event_category(event_type: AuditEventType) -> str:
    """Get category for an event type."""
    categories = {
        "widget": ["widget_opened", "widget_closed", "widget_error"],
        "user_action": ["mode_selected", "amount_entered", "currency_selected", "wallet_entered"],
        "order": ["order_created", "order_linked", "order_completed", "order_cancelled", "order_failed", "order_refunded"],
        "kyc": ["kyc_started", "kyc_completed", "kyc_failed"],
        "payment": ["payment_initiated", "payment_received", "payment_failed"],
        "transfer": ["crypto_transfer_initiated", "crypto_transfer_completed", "fiat_transfer_initiated", "fiat_transfer_completed"],
        "system": ["webhook_received", "status_update", "error_occurred"]
    }
    
    for category, events in categories.items():
        if event_type.value in events:
            return category
    
    return "other"

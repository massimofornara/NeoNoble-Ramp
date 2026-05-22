"""
Webhook routes and admin endpoints for payout management.

Handles:
- Stripe payout webhooks
- Pending transfer management
"""

from fastapi import APIRouter, Request, HTTPException, Header, Query
from pydantic import BaseModel
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks & Payouts"])

# Service will be set by main app
payout_service = None


def set_payout_service(service):
    global payout_service
    payout_service = service


class MarkCompletedRequest(BaseModel):
    quote_id: str
    external_reference: Optional[str] = None


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature")
):
    """
    Handle Stripe webhook events.
    
    Events handled:
    - payout.paid: Payout completed successfully
    - payout.failed: Payout failed
    - payout.canceled: Payout was canceled
    """
    if not stripe_signature:
        logger.warning("Stripe webhook received without signature header")
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
    
    payload = await request.body()
    
    success, error = await payout_service.handle_webhook(payload, stripe_signature)
    
    if not success:
        logger.error(f"Stripe webhook processing failed: {error}")
        return {"status": "error", "message": error}
    
    return {"status": "success"}


@router.get("/transfers/pending")
async def list_pending_transfers():
    """
    List all pending SEPA transfers that need manual processing.
    
    Returns transfers with status 'pending_transfer' including
    full SEPA details for wire execution.
    """
    transfers = await payout_service.list_pending_transfers()
    return {
        "count": len(transfers),
        "transfers": transfers
    }


@router.get("/transfers/summary")
async def get_transfer_summary():
    """
    Get summary of all transfers by status.
    
    Returns counts and totals grouped by status,
    plus Stripe account info.
    """
    summary = await payout_service.get_transfer_summary()
    return summary


@router.get("/transfers")
async def list_transfers(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100)
):
    """
    List all transfers with optional status filter.
    """
    transfers = await payout_service.list_payouts(limit=limit, status=status)
    return {
        "count": len(transfers),
        "transfers": transfers
    }


@router.get("/transfers/{quote_id}")
async def get_transfer(quote_id: str):
    """
    Get transfer details by quote ID.
    """
    transfer = await payout_service.get_payout_by_quote(quote_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return transfer


@router.post("/transfers/mark-completed")
async def mark_transfer_completed(request: MarkCompletedRequest):
    """
    Mark a pending transfer as completed after manual SEPA execution.
    
    Call this endpoint after you've manually executed the SEPA wire transfer.
    """
    success = await payout_service.mark_transfer_completed(
        quote_id=request.quote_id,
        external_ref=request.external_reference
    )
    
    if not success:
        raise HTTPException(
            status_code=400, 
            detail="Transfer not found or not in pending_transfer status"
        )
    
    return {
        "status": "success",
        "message": f"Transfer for quote {request.quote_id} marked as completed"
    }

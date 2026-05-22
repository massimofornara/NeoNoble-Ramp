"""
Stripe Payout Webhook Routes.

Handles Stripe webhook events for payout status updates.
Events handled:
- payout.paid: Payout was successful
- payout.failed: Payout failed
- payout.canceled: Payout was canceled
- payout.created: Payout was created
- payout.updated: Payout status changed
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import logging
from typing import Optional

from services.real_payout_service import get_real_payout_service, RealPayoutService
from services.por_engine import InternalPoRProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stripe", tags=["Stripe Webhooks"])

# Service references
_payout_service: Optional[RealPayoutService] = None
_por_engine: Optional[InternalPoRProvider] = None


def set_payout_service(service: RealPayoutService):
    """Set the payout service instance."""
    global _payout_service
    _payout_service = service


def set_por_engine(engine: InternalPoRProvider):
    """Set the PoR engine instance."""
    global _por_engine
    _por_engine = engine


@router.post("/webhook/payout")
async def handle_stripe_payout_webhook(request: Request):
    """
    Handle Stripe payout webhook events.
    
    This endpoint receives webhook events from Stripe when payout status changes:
    - payout.paid: Funds have been transferred to bank account
    - payout.failed: Payout failed (insufficient balance, invalid account, etc.)
    - payout.canceled: Payout was canceled
    
    The webhook updates the PoR transaction state accordingly.
    
    **Security**: Webhook signature is verified using STRIPE_WEBHOOK_SECRET
    """
    payout_service = _payout_service or get_real_payout_service()
    
    if not payout_service:
        logger.error("Payout service not configured")
        return JSONResponse(
            status_code=500,
            content={"error": "Payout service not configured"}
        )
    
    # Get raw payload and signature
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")
    
    if not sig_header:
        logger.warning("Missing Stripe-Signature header")
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
    
    # Process webhook
    success, error, event_data = await payout_service.handle_webhook(payload, sig_header)
    
    if not success:
        logger.error(f"Webhook processing failed: {error}")
        raise HTTPException(status_code=400, detail=error)
    
    # If we have event data and a PoR engine, update the transaction
    if event_data and _por_engine:
        event_type = event_data.get('event')
        quote_id = event_data.get('quote_id')
        payout_id = event_data.get('payout_id')
        
        if quote_id and event_type in ['payout.paid', 'payout.failed', 'payout.canceled']:
            logger.info(f"Updating PoR transaction {quote_id} based on {event_type}")
            
            # Map Stripe event to status
            status_map = {
                'payout.paid': 'paid',
                'payout.failed': 'failed',
                'payout.canceled': 'canceled'
            }
            
            await _por_engine.handle_payout_webhook(
                quote_id=quote_id,
                payout_status=status_map.get(event_type, 'unknown'),
                payout_id=payout_id,
                failure_code=event_data.get('failure_code'),
                failure_message=event_data.get('failure_message')
            )
            
            # Check if card fallback is needed
            if event_data.get('requires_fallback'):
                logger.info(f"Card fallback requested for quote {quote_id}")
                # The payout service will handle this in subsequent requests
    
    logger.info(f"Stripe webhook processed successfully: {event_data}")
    
    return JSONResponse(
        status_code=200,
        content={"status": "processed", "data": event_data}
    )


@router.get("/payout/{quote_id}")
async def get_payout_status(quote_id: str):
    """
    Get payout status for a quote.
    
    Returns the current payout status including Stripe payout ID and details.
    """
    payout_service = _payout_service or get_real_payout_service()
    
    if not payout_service:
        raise HTTPException(status_code=500, detail="Payout service not configured")
    
    payout = await payout_service.get_payout_by_quote(quote_id)
    
    if not payout:
        raise HTTPException(status_code=404, detail=f"Payout not found for quote: {quote_id}")
    
    return payout


@router.get("/payouts")
async def list_payouts(status: Optional[str] = None, limit: int = 50):
    """
    List recent payouts.
    
    Args:
        status: Filter by status (pending, paid, failed, etc.)
        limit: Maximum number of results (default: 50)
    """
    payout_service = _payout_service or get_real_payout_service()
    
    if not payout_service:
        raise HTTPException(status_code=500, detail="Payout service not configured")
    
    payouts = await payout_service.list_payouts(status=status, limit=limit)
    
    return {
        "payouts": payouts,
        "count": len(payouts),
        "filter": {"status": status, "limit": limit}
    }


@router.get("/payouts/summary")
async def get_payout_summary():
    """
    Get payout summary statistics.
    
    Returns aggregated payout data by status and Stripe balance info.
    """
    payout_service = _payout_service or get_real_payout_service()
    
    if not payout_service:
        raise HTTPException(status_code=500, detail="Payout service not configured")
    
    summary = await payout_service.get_payout_summary()
    
    return summary

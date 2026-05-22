"""
Liquidity API Routes.

Provides API endpoints for the Hybrid PoR Liquidity Architecture:
- Treasury management and ledger queries
- Exposure tracking and summaries
- Market routing status
- Hedging policies and events
- Reconciliation batches and reports
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import logging

from services.liquidity import (
    get_treasury_service,
    get_exposure_service,
    get_routing_service,
    get_hedging_service,
    get_reconciliation_service
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/liquidity", tags=["Liquidity"])


# ============================================================================
# TREASURY ENDPOINTS
# ============================================================================

@router.get("/treasury/summary")
async def get_treasury_summary():
    """
    Get comprehensive treasury summary.
    
    Returns balances, coverage ratio, and recent ledger entries.
    """
    treasury = get_treasury_service()
    if not treasury:
        raise HTTPException(status_code=500, detail="Treasury service not initialized")
    
    return await treasury.get_treasury_summary()


@router.get("/treasury/balances")
async def get_treasury_balances():
    """Get current treasury balances by currency."""
    treasury = get_treasury_service()
    if not treasury:
        raise HTTPException(status_code=500, detail="Treasury service not initialized")
    
    balances = await treasury.get_all_balances()
    total_eur = await treasury.get_total_eur_equivalent()
    
    return {
        "balances": balances,
        "total_eur_equivalent": total_eur,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/treasury/ledger")
async def get_treasury_ledger(
    quote_id: Optional[str] = None,
    entry_type: Optional[str] = None,
    start_sequence: Optional[int] = None,
    end_sequence: Optional[int] = None,
    limit: int = Query(default=100, le=500)
):
    """
    Query treasury ledger entries.
    
    Supports filtering by quote_id, entry_type, and sequence range.
    """
    treasury = get_treasury_service()
    if not treasury:
        raise HTTPException(status_code=500, detail="Treasury service not initialized")
    
    from models.liquidity.treasury_models import LedgerEntryType
    
    entry_type_enum = None
    if entry_type:
        try:
            entry_type_enum = LedgerEntryType(entry_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid entry type: {entry_type}")
    
    entries = await treasury.get_ledger_entries(
        quote_id=quote_id,
        entry_type=entry_type_enum,
        start_sequence=start_sequence,
        end_sequence=end_sequence,
        limit=limit
    )
    
    return {
        "entries": entries,
        "count": len(entries),
        "filters": {
            "quote_id": quote_id,
            "entry_type": entry_type,
            "start_sequence": start_sequence,
            "end_sequence": end_sequence,
            "limit": limit
        }
    }


@router.get("/treasury/snapshot")
async def get_treasury_snapshot():
    """Get latest treasury snapshot."""
    treasury = get_treasury_service()
    if not treasury:
        raise HTTPException(status_code=500, detail="Treasury service not initialized")
    
    exposure = get_exposure_service()
    total_exposure = 0.0
    if exposure:
        total_exposure = await exposure.get_total_active_exposure()
    
    snapshot = await treasury.create_snapshot(total_exposure_eur=total_exposure)
    
    return snapshot.to_dict()


@router.get("/treasury/integrity")
async def verify_ledger_integrity(
    start_sequence: int = Query(default=1, ge=1),
    end_sequence: Optional[int] = None
):
    """
    Verify treasury ledger chain integrity.
    
    Checks sequence continuity, hash chain, and balance calculations.
    """
    treasury = get_treasury_service()
    if not treasury:
        raise HTTPException(status_code=500, detail="Treasury service not initialized")
    
    is_valid, discrepancies = await treasury.verify_ledger_integrity(
        start_sequence=start_sequence,
        end_sequence=end_sequence
    )
    
    return {
        "is_valid": is_valid,
        "discrepancies": discrepancies,
        "checked_range": {
            "start_sequence": start_sequence,
            "end_sequence": end_sequence or "latest"
        }
    }


# ============================================================================
# EXPOSURE ENDPOINTS
# ============================================================================

@router.get("/exposure/summary")
async def get_exposure_summary():
    """Get exposure summary with aggregations."""
    exposure = get_exposure_service()
    if not exposure:
        raise HTTPException(status_code=500, detail="Exposure service not initialized")
    
    summary = await exposure.get_exposure_summary()
    return summary.to_dict()


@router.get("/exposure/active")
async def get_active_exposures(limit: int = Query(default=50, le=200)):
    """Get all active (uncovered) exposures."""
    exposure = get_exposure_service()
    if not exposure:
        raise HTTPException(status_code=500, detail="Exposure service not initialized")
    
    exposures = await exposure.get_active_exposures(limit=limit)
    total = await exposure.get_total_active_exposure()
    
    return {
        "exposures": exposures,
        "count": len(exposures),
        "total_active_exposure_eur": total
    }


@router.get("/exposure/{exposure_id}")
async def get_exposure(exposure_id: str):
    """Get exposure by ID."""
    exposure_svc = get_exposure_service()
    if not exposure_svc:
        raise HTTPException(status_code=500, detail="Exposure service not initialized")
    
    exposure = await exposure_svc.get_exposure(exposure_id)
    if not exposure:
        raise HTTPException(status_code=404, detail=f"Exposure not found: {exposure_id}")
    
    return exposure


@router.get("/exposure/{exposure_id}/reconstruct")
async def reconstruct_exposure(exposure_id: str):
    """
    Reconstruct full exposure record with all references.
    
    Returns all linked data for audit trail reconstruction:
    - On-chain deposit reference
    - Payout provider reference
    - Treasury position snapshot
    - Coverage events
    - Reconciliation batch reference
    """
    exposure_svc = get_exposure_service()
    if not exposure_svc:
        raise HTTPException(status_code=500, detail="Exposure service not initialized")
    
    reconstruction = await exposure_svc.reconstruct_exposure(exposure_id)
    if "error" in reconstruction:
        raise HTTPException(status_code=404, detail=reconstruction["error"])
    
    return reconstruction


@router.get("/exposure/by-quote/{quote_id}")
async def get_exposure_by_quote(quote_id: str):
    """Get exposure by quote ID."""
    exposure_svc = get_exposure_service()
    if not exposure_svc:
        raise HTTPException(status_code=500, detail="Exposure service not initialized")
    
    exposure = await exposure_svc.get_exposure_by_quote(quote_id)
    if not exposure:
        raise HTTPException(status_code=404, detail=f"Exposure not found for quote: {quote_id}")
    
    return exposure


# ============================================================================
# MARKET ROUTING ENDPOINTS
# ============================================================================

@router.get("/routing/summary")
async def get_routing_summary():
    """Get market routing service summary."""
    routing = get_routing_service()
    if not routing:
        raise HTTPException(status_code=500, detail="Routing service not initialized")
    
    return await routing.get_routing_summary()


@router.get("/routing/path")
async def get_conversion_path(
    source: str = Query(..., description="Source currency (e.g., NENO)"),
    destination: str = Query(..., description="Destination currency (e.g., EUR)"),
    amount: float = Query(..., gt=0, description="Amount to convert")
):
    """
    Get optimal conversion path for a currency pair.
    
    Returns routing steps, estimated rates, and execution time.
    """
    routing = get_routing_service()
    if not routing:
        raise HTTPException(status_code=500, detail="Routing service not initialized")
    
    path = await routing.get_conversion_path(source, destination, amount)
    if not path:
        raise HTTPException(
            status_code=404, 
            detail=f"No conversion path available for {source} -> {destination}"
        )
    
    return path.to_dict()


@router.get("/routing/conversions")
async def get_conversions(
    quote_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200)
):
    """Get market conversion events."""
    routing = get_routing_service()
    if not routing:
        raise HTTPException(status_code=500, detail="Routing service not initialized")
    
    if quote_id:
        conversions = await routing.get_conversions_by_quote(quote_id)
    else:
        # Get all recent conversions
        cursor = routing.conversions_collection.find(
            {"status": status} if status else {},
            {"_id": 0}
        ).sort("created_at", -1).limit(limit)
        conversions = await cursor.to_list(length=limit)
    
    return {
        "conversions": conversions,
        "count": len(conversions),
        "shadow_mode": True  # Phase 1 is shadow mode only
    }


# ============================================================================
# HEDGING ENDPOINTS
# ============================================================================

@router.get("/hedging/summary")
async def get_hedging_summary():
    """Get hedging service summary including policy and recent proposals."""
    hedging = get_hedging_service()
    if not hedging:
        raise HTTPException(status_code=500, detail="Hedging service not initialized")
    
    return await hedging.get_hedging_summary()


@router.get("/hedging/policy")
async def get_hedge_policy():
    """Get current hedge policy configuration."""
    hedging = get_hedging_service()
    if not hedging:
        raise HTTPException(status_code=500, detail="Hedging service not initialized")
    
    return hedging._default_policy.to_dict()


@router.get("/hedging/proposals")
async def get_hedge_proposals(limit: int = Query(default=20, le=100)):
    """
    Get recent hedge proposals (shadow mode output).
    
    Proposals show what hedges would be triggered based on current policy.
    """
    hedging = get_hedging_service()
    if not hedging:
        raise HTTPException(status_code=500, detail="Hedging service not initialized")
    
    proposals = await hedging.get_recent_proposals(limit=limit)
    
    return {
        "proposals": proposals,
        "count": len(proposals),
        "shadow_mode": True
    }


@router.get("/hedging/events")
async def get_hedge_events(limit: int = Query(default=50, le=200)):
    """Get hedge events."""
    hedging = get_hedging_service()
    if not hedging:
        raise HTTPException(status_code=500, detail="Hedging service not initialized")
    
    hedges = await hedging.get_recent_hedges(limit=limit)
    
    return {
        "hedges": hedges,
        "count": len(hedges),
        "shadow_mode": True
    }


@router.post("/hedging/evaluate")
async def evaluate_hedge_triggers():
    """
    Manually trigger hedge evaluation.
    
    Returns a hedge proposal if triggers are met.
    """
    hedging = get_hedging_service()
    exposure_svc = get_exposure_service()
    treasury = get_treasury_service()
    
    if not hedging or not exposure_svc or not treasury:
        raise HTTPException(status_code=500, detail="Services not initialized")
    
    # Get current state
    total_exposure = await exposure_svc.get_total_active_exposure()
    coverage_ratio = await treasury.calculate_coverage_ratio(total_exposure)
    active_exposures = await exposure_svc.get_active_exposures(limit=20)
    active_ids = [e["exposure_id"] for e in active_exposures]
    
    # Evaluate
    proposal = await hedging.evaluate_hedge_triggers(
        total_exposure_eur=total_exposure,
        coverage_ratio=coverage_ratio,
        active_exposure_ids=active_ids
    )
    
    if proposal:
        return {
            "triggered": True,
            "proposal": proposal.to_dict()
        }
    
    return {
        "triggered": False,
        "current_state": {
            "total_exposure_eur": total_exposure,
            "coverage_ratio": coverage_ratio,
            "active_exposures": len(active_ids)
        }
    }


# ============================================================================
# RECONCILIATION ENDPOINTS
# ============================================================================

@router.get("/reconciliation/summary")
async def get_reconciliation_summary():
    """Get reconciliation service summary."""
    recon = get_reconciliation_service()
    if not recon:
        raise HTTPException(status_code=500, detail="Reconciliation service not initialized")
    
    return await recon.get_reconciliation_summary()


@router.get("/reconciliation/batches")
async def get_settlement_batches(limit: int = Query(default=20, le=100)):
    """Get recent settlement batches."""
    recon = get_reconciliation_service()
    if not recon:
        raise HTTPException(status_code=500, detail="Reconciliation service not initialized")
    
    batches = await recon.get_recent_batches(limit=limit)
    
    return {
        "batches": batches,
        "count": len(batches)
    }


@router.get("/reconciliation/batch/{batch_id}")
async def get_batch(batch_id: str):
    """Get settlement batch by ID."""
    recon = get_reconciliation_service()
    if not recon:
        raise HTTPException(status_code=500, detail="Reconciliation service not initialized")
    
    batch = await recon.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")
    
    return batch


@router.get("/reconciliation/coverage")
async def get_coverage_events(
    exposure_id: Optional[str] = None,
    limit: int = Query(default=50, le=200)
):
    """Get coverage events."""
    recon = get_reconciliation_service()
    if not recon:
        raise HTTPException(status_code=500, detail="Reconciliation service not initialized")
    
    events = await recon.get_coverage_events(exposure_id=exposure_id, limit=limit)
    
    return {
        "coverage_events": events,
        "count": len(events)
    }


# ============================================================================
# DASHBOARD ENDPOINT
# ============================================================================

@router.get("/dashboard")
async def get_liquidity_dashboard():
    """
    Get comprehensive liquidity dashboard.
    
    Returns combined summary from all liquidity services.
    """
    treasury = get_treasury_service()
    exposure_svc = get_exposure_service()
    routing = get_routing_service()
    hedging = get_hedging_service()
    recon = get_reconciliation_service()
    
    dashboard = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "hybrid",  # Phase 1: real treasury, shadow routing/hedging
        "services": {
            "treasury": treasury is not None,
            "exposure": exposure_svc is not None,
            "routing": routing is not None,
            "hedging": hedging is not None,
            "reconciliation": recon is not None
        }
    }
    
    # Treasury summary
    if treasury:
        balances = await treasury.get_all_balances()
        total_eur = await treasury.get_total_eur_equivalent()
        dashboard["treasury"] = {
            "balances": balances,
            "total_eur_equivalent": total_eur
        }
    
    # Exposure summary
    if exposure_svc:
        exposure_summary = await exposure_svc.get_exposure_summary()
        total_active = await exposure_svc.get_total_active_exposure()
        dashboard["exposure"] = {
            "total_active_eur": total_active,
            "summary": exposure_summary.to_dict()
        }
    
    # Coverage ratio
    if treasury and exposure_svc:
        total_exposure = await exposure_svc.get_total_active_exposure()
        coverage_ratio = await treasury.calculate_coverage_ratio(total_exposure)
        dashboard["coverage_ratio"] = coverage_ratio if coverage_ratio != float('inf') else 999.99
    
    # Routing summary
    if routing:
        routing_summary = await routing.get_routing_summary()
        dashboard["routing"] = {
            "shadow_mode": routing_summary.get("shadow_mode", True),
            "conversions_by_status": routing_summary.get("by_status", {})
        }
    
    # Hedging summary
    if hedging:
        hedging_summary = await hedging.get_hedging_summary()
        dashboard["hedging"] = {
            "shadow_mode": hedging_summary.get("shadow_mode", True),
            "volatility_locked": hedging_summary.get("volatility_locked", False),
            "hedges_by_status": hedging_summary.get("by_status", {}),
            "recent_proposals_count": len(hedging_summary.get("recent_proposals", []))
        }
    
    # Reconciliation summary
    if recon:
        recon_summary = await recon.get_reconciliation_summary()
        dashboard["reconciliation"] = {
            "pending_batches": recon_summary.get("pending_batches", 0),
            "batch_statistics": recon_summary.get("batch_statistics", {})
        }
    
    return dashboard

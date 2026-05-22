"""
Monitoring & Audit API Routes.

Provides endpoints for:
- System health monitoring
- Audit log access
- PoR engine metrics
- Settlement statistics
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging
import os
from datetime import datetime, timezone

from services.audit_logger import AuditLogger, AuditEventType, get_audit_logger
from services.por_engine import InternalPoRProvider
from services.settlement_service import SettlementService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["Monitoring & Audit"])

# Services will be set by main app
audit_logger_service: AuditLogger = None
por_engine: InternalPoRProvider = None
settlement_service: SettlementService = None


def set_monitoring_services(
    audit: AuditLogger,
    por: InternalPoRProvider,
    settlement: SettlementService
):
    global audit_logger_service, por_engine, settlement_service
    audit_logger_service = audit
    por_engine = por
    settlement_service = settlement


@router.get("/health")
async def get_system_health():
    """
    Get comprehensive system health status.
    
    Returns status of all PoR engine components.
    """
    health = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {
            "por_engine": {
                "status": "up" if por_engine and por_engine.is_available() else "down",
                "settlement_mode": por_engine.config.settlement_mode.value if por_engine else "unknown"
            },
            "settlement_service": {
                "status": "up" if settlement_service else "down"
            },
            "audit_logger": {
                "status": "up" if audit_logger_service else "down"
            },
            "blockchain_monitoring": {
                "status": "up" if os.environ.get("BSC_RPC_URL") else "disabled"
            },
            "wallet_service": {
                "status": "up" if os.environ.get("NENO_WALLET_MNEMONIC") else "disabled"
            }
        },
        "version": "2.0.0"
    }
    
    # Set overall status
    if health["components"]["por_engine"]["status"] == "down":
        health["status"] = "degraded"
    
    return health


@router.get("/metrics")
async def get_por_metrics():
    """
    Get PoR engine metrics and statistics.
    """
    if not por_engine:
        raise HTTPException(status_code=503, detail="PoR engine not available")
    
    # Get transaction counts by state
    from services.provider_interface import TransactionState
    
    state_counts = {}
    for state in TransactionState:
        transactions = await por_engine.list_transactions(state=state, limit=1000)
        state_counts[state.value] = len(transactions)
    
    # Get liquidity status
    liquidity = await por_engine.get_liquidity_status()
    
    # Get settlement stats
    settlement_stats = await settlement_service.get_statistics() if settlement_service else {}
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "transactions": {
            "by_state": state_counts,
            "total": sum(state_counts.values())
        },
        "liquidity": liquidity,
        "settlement": settlement_stats,
        "config": {
            "settlement_mode": por_engine.config.settlement_mode.value,
            "fee_percentage": por_engine.config.fee_percentage,
            "neno_price_eur": 10000.0
        }
    }


@router.get("/audit/trail/{quote_id}")
async def get_audit_trail(quote_id: str):
    """
    Get complete audit trail for a specific quote.
    
    Returns all audit events related to the quote in chronological order.
    """
    if not audit_logger_service:
        raise HTTPException(status_code=503, detail="Audit logger not available")
    
    trail = await audit_logger_service.get_audit_trail(quote_id)
    
    return {
        "quote_id": quote_id,
        "event_count": len(trail),
        "events": trail
    }


@router.get("/audit/events")
async def get_audit_events(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Get recent audit events.
    
    Optionally filter by event type.
    """
    if not audit_logger_service:
        raise HTTPException(status_code=503, detail="Audit logger not available")
    
    event_filter = None
    if event_type:
        try:
            event_filter = AuditEventType(event_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid event type. Valid types: {[e.value for e in AuditEventType]}"
            )
    
    events = await audit_logger_service.get_recent_events(
        event_type=event_filter,
        limit=limit
    )
    
    return {
        "count": len(events),
        "events": events
    }


@router.get("/audit/event-types")
async def get_event_types():
    """
    Get all available audit event types.
    """
    return {
        "event_types": [
            {
                "value": e.value,
                "category": e.value.split(".")[0]
            }
            for e in AuditEventType
        ]
    }


@router.get("/config")
async def get_system_config():
    """
    Get current system configuration (non-sensitive).
    """
    return {
        "por_engine": {
            "name": por_engine.config.name if por_engine else "N/A",
            "settlement_mode": por_engine.config.settlement_mode.value if por_engine else "N/A",
            "fee_percentage": por_engine.config.fee_percentage if por_engine else "N/A",
            "supported_cryptos": por_engine.config.supported_cryptos if por_engine else [],
            "kyc_required": por_engine.config.kyc_required if por_engine else "N/A",
            "aml_required": por_engine.config.aml_required if por_engine else "N/A"
        },
        "environment": {
            "quote_ttl_minutes": int(os.environ.get("QUOTE_TTL_MINUTES", 60)),
            "blockchain_enabled": bool(os.environ.get("BSC_RPC_URL")),
            "wallet_enabled": bool(os.environ.get("NENO_WALLET_MNEMONIC")),
            "stripe_enabled": bool(os.environ.get("STRIPE_SECRET_KEY"))
        }
    }



@router.get("/architecture")
async def get_architecture_plan():
    """Get the microservices architecture decomposition plan."""
    from services.service_registry import get_microservice_plan, DOMAIN_GROUPS
    return {
        "plan": get_microservice_plan(),
        "domains": DOMAIN_GROUPS,
        "current": "monolith",
        "ready_for_split": True,
    }

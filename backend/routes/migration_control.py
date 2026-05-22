"""
Migration Control API Routes.

Provides administrative endpoints for controlling the PostgreSQL migration:
- Migration status monitoring
- Phase transitions
- Validation execution
- Rollback control

IMPORTANT: These endpoints should be protected in production.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

from database.dual_manager import (
    DualDatabaseManager,
    DatabaseMode,
    MigrationPhase,
    get_dual_db_manager
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/migration", tags=["Migration Control"])


# ========================
# Status Endpoints
# ========================

@router.get("/status")
async def get_migration_status():
    """
    Get current migration status.
    
    Returns comprehensive status including:
    - Current phase and mode
    - Database connectivity
    - Write/read metrics
    - Validation status
    """
    manager = get_dual_db_manager()
    return manager.get_status()


@router.get("/health")
async def get_migration_health():
    """
    Get migration health check.
    
    Quick health check for monitoring systems.
    """
    manager = get_dual_db_manager()
    status = manager.get_status()
    
    healthy = (
        status["initialized"] and
        status["mongodb_connected"] and
        (not manager.is_postgresql_enabled or status["postgresql_connected"])
    )
    
    return {
        "healthy": healthy,
        "mode": status["mode"],
        "phase": status["phase"],
        "consistency_failures": status["metrics"]["consistency_failures"]
    }


# ========================
# Phase Control Endpoints
# ========================

@router.post("/start")
async def start_migration():
    """
    Start the migration process.
    
    Enters shadow mode where writes go to MongoDB
    and are shadowed to PostgreSQL for validation.
    """
    manager = get_dual_db_manager()
    
    if manager.state.phase != MigrationPhase.NOT_STARTED:
        raise HTTPException(
            status_code=400,
            detail=f"Migration already started (phase: {manager.state.phase.value})"
        )
    
    await manager.start_migration()
    
    return {
        "message": "Migration started",
        "phase": manager.state.phase.value,
        "mode": manager.state.mode.value
    }


@router.post("/enable-dual-write")
async def enable_dual_write():
    """
    Enable dual-write mode.
    
    All writes go to both MongoDB and PostgreSQL.
    Reads continue from MongoDB.
    """
    manager = get_dual_db_manager()
    
    if manager.state.phase not in [MigrationPhase.STAGING, MigrationPhase.VALIDATION]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot enable dual-write from phase: {manager.state.phase.value}"
        )
    
    await manager.enable_dual_write()
    
    return {
        "message": "Dual-write mode enabled",
        "phase": manager.state.phase.value,
        "mode": manager.state.mode.value
    }


@router.post("/switch-primary")
async def switch_to_postgresql():
    """
    Switch primary reads to PostgreSQL.
    
    Writes continue to both databases.
    Reads now come from PostgreSQL.
    
    CAUTION: Run validation before this step.
    """
    manager = get_dual_db_manager()
    
    if manager.state.phase != MigrationPhase.DUAL_WRITE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot switch primary from phase: {manager.state.phase.value}"
        )
    
    # Check validation status
    if not manager.state.validation_passed:
        raise HTTPException(
            status_code=400,
            detail="Validation has not passed. Run validation first."
        )
    
    await manager.switch_to_postgresql()
    
    return {
        "message": "Switched primary to PostgreSQL",
        "phase": manager.state.phase.value,
        "mode": manager.state.mode.value
    }


@router.post("/complete")
async def complete_migration(force: bool = Query(False, description="Force completion without validation check")):
    """
    Complete migration - PostgreSQL only mode.
    
    Disables MongoDB writes entirely.
    
    CAUTION: This should only be done after thorough validation.
    Use force=true only if validation has been confirmed externally.
    """
    manager = get_dual_db_manager()
    
    # Allow completion from validation or cutover phase
    if manager.state.phase not in [MigrationPhase.CUTOVER, MigrationPhase.VALIDATION]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot complete migration from phase: {manager.state.phase.value}"
        )
    
    # Require recent successful validation (unless forced)
    if not force and not manager.state.validation_passed:
        raise HTTPException(
            status_code=400,
            detail="Final validation required before completion. Use force=true to override if validation confirmed externally."
        )
    
    await manager.complete_migration()
    
    return {
        "message": "Migration completed - PostgreSQL only mode",
        "phase": manager.state.phase.value,
        "mode": manager.state.mode.value,
        "completed_at": manager.state.completed_at.isoformat(),
        "forced": force
    }


@router.post("/rollback")
async def rollback_migration(reason: Optional[str] = Query(None, description="Reason for rollback")):
    """
    Rollback to MongoDB.
    
    Immediately reverts to MongoDB-only mode.
    Safe to call at any migration phase.
    """
    manager = get_dual_db_manager()
    
    rollback_reason = reason or "Manual rollback via API"
    await manager.rollback(rollback_reason)
    
    return {
        "message": "Rolled back to MongoDB",
        "phase": manager.state.phase.value,
        "mode": manager.state.mode.value,
        "reason": rollback_reason
    }


# ========================
# Validation Endpoints
# ========================

@router.post("/validate")
async def run_validation():
    """
    Run comprehensive validation.
    
    Compares data between MongoDB and PostgreSQL:
    - Record counts
    - Recent transaction data
    - State consistency
    
    Returns detailed validation report.
    """
    manager = get_dual_db_manager()
    
    if not manager.is_postgresql_enabled:
        raise HTTPException(
            status_code=400,
            detail="PostgreSQL not enabled in current mode"
        )
    
    report = await manager.run_validation()
    
    return report


@router.get("/validation-history")
async def get_validation_history():
    """
    Get validation history and errors.
    """
    manager = get_dual_db_manager()
    
    return {
        "last_validation": manager.state.last_validation.isoformat() if manager.state.last_validation else None,
        "validation_passed": manager.state.validation_passed,
        "recent_errors": manager.state.validation_errors[-20:]  # Last 20 errors
    }


# ========================
# Mode Control Endpoints
# ========================

@router.post("/set-mode/{mode}")
async def set_database_mode(mode: str):
    """
    Directly set database mode.
    
    CAUTION: This bypasses normal phase transitions.
    Use for emergency control only.
    
    Valid modes:
    - mongodb_only
    - postgresql_only
    - dual_write
    - dual_read_pg
    - shadow_mode
    """
    try:
        db_mode = DatabaseMode(mode.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode. Valid modes: {[m.value for m in DatabaseMode]}"
        )
    
    manager = get_dual_db_manager()
    await manager.set_mode(db_mode)
    
    return {
        "message": f"Mode set to {mode}",
        "mode": manager.state.mode.value,
        "phase": manager.state.phase.value
    }


# ========================
# Metrics Endpoints
# ========================

@router.get("/metrics")
async def get_migration_metrics():
    """
    Get migration metrics.
    
    Returns write/read counts and consistency statistics.
    """
    manager = get_dual_db_manager()
    
    return {
        "mode": manager.state.mode.value,
        "phase": manager.state.phase.value,
        "metrics": {
            "mongodb_writes": manager.state.mongodb_writes,
            "postgresql_writes": manager.state.postgresql_writes,
            "read_operations": manager.state.read_operations,
            "consistency_checks": manager.state.consistency_checks,
            "consistency_failures": manager.state.consistency_failures,
            "consistency_rate": (
                (1 - manager.state.consistency_failures / max(manager.state.consistency_checks, 1)) * 100
                if manager.state.consistency_checks > 0 else 100.0
            )
        }
    }


@router.post("/reset-metrics")
async def reset_metrics():
    """
    Reset migration metrics.
    
    Useful for starting fresh metric collection after validation.
    """
    manager = get_dual_db_manager()
    
    manager.state.mongodb_writes = 0
    manager.state.postgresql_writes = 0
    manager.state.read_operations = 0
    manager.state.consistency_checks = 0
    manager.state.consistency_failures = 0
    
    return {"message": "Metrics reset"}

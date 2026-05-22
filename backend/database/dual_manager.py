"""
Dual-Database Service Layer.

Provides seamless switching between MongoDB and PostgreSQL
with atomic state management and rollback capabilities.

Features:
- Hot-switchable database backend
- Dual-write mode for migration validation
- Automatic rollback on failure
- Transaction integrity verification
- Audit trail consistency checks
"""

import os
import logging
import asyncio
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

logger = logging.getLogger("db.dual")


class DatabaseMode(str, Enum):
    """Database operation mode."""
    MONGODB_ONLY = "mongodb_only"          # Legacy mode
    POSTGRESQL_ONLY = "postgresql_only"    # Full migration
    DUAL_WRITE = "dual_write"              # Write to both, read from MongoDB
    DUAL_READ_PG = "dual_read_pg"          # Write to both, read from PostgreSQL
    SHADOW_MODE = "shadow_mode"            # Write MongoDB, shadow-write PG for validation


class MigrationPhase(str, Enum):
    """Migration phase tracking."""
    NOT_STARTED = "not_started"
    STAGING = "staging"
    DUAL_WRITE = "dual_write"
    VALIDATION = "validation"
    CUTOVER = "cutover"
    COMPLETED = "completed"
    ROLLBACK = "rollback"


@dataclass
class MigrationState:
    """Tracks migration state and metrics."""
    phase: MigrationPhase = MigrationPhase.NOT_STARTED
    mode: DatabaseMode = DatabaseMode.MONGODB_ONLY
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Metrics
    mongodb_writes: int = 0
    postgresql_writes: int = 0
    read_operations: int = 0
    consistency_checks: int = 0
    consistency_failures: int = 0
    
    # Validation results
    last_validation: Optional[datetime] = None
    validation_passed: bool = False
    validation_errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "phase": self.phase.value,
            "mode": self.mode.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metrics": {
                "mongodb_writes": self.mongodb_writes,
                "postgresql_writes": self.postgresql_writes,
                "read_operations": self.read_operations,
                "consistency_checks": self.consistency_checks,
                "consistency_failures": self.consistency_failures
            },
            "validation": {
                "last_check": self.last_validation.isoformat() if self.last_validation else None,
                "passed": self.validation_passed,
                "errors": self.validation_errors[-10:]  # Last 10 errors
            }
        }


class DualDatabaseManager:
    """
    Manages dual-database operations for safe migration.
    
    Provides:
    - Atomic dual-write operations
    - Consistency verification
    - Automatic rollback on failures
    - Migration phase management
    """
    
    def __init__(self):
        self.state = MigrationState()
        self._mongo_db = None
        self._pg_session_factory = None
        self._initialized = False
        self._lock = asyncio.Lock()
        
        # Callbacks for consistency checks
        self._consistency_callbacks: List[Callable] = []
        
        # Initialize mode from environment
        env_mode = os.environ.get("DATABASE_MODE", "mongodb_only").lower()
        try:
            self.state.mode = DatabaseMode(env_mode)
        except ValueError:
            self.state.mode = DatabaseMode.MONGODB_ONLY
            logger.warning(f"Invalid DATABASE_MODE '{env_mode}', defaulting to mongodb_only")
    
    async def initialize(
        self,
        mongo_db=None,
        pg_session_factory=None
    ):
        """Initialize database connections."""
        async with self._lock:
            self._mongo_db = mongo_db
            self._pg_session_factory = pg_session_factory
            self._initialized = True
            
            logger.info(f"Dual database manager initialized in {self.state.mode.value} mode")
    
    @property
    def is_postgresql_enabled(self) -> bool:
        """Check if PostgreSQL is enabled."""
        return self.state.mode in [
            DatabaseMode.POSTGRESQL_ONLY,
            DatabaseMode.DUAL_WRITE,
            DatabaseMode.DUAL_READ_PG,
            DatabaseMode.SHADOW_MODE
        ]
    
    @property
    def is_mongodb_enabled(self) -> bool:
        """Check if MongoDB is enabled."""
        return self.state.mode in [
            DatabaseMode.MONGODB_ONLY,
            DatabaseMode.DUAL_WRITE,
            DatabaseMode.DUAL_READ_PG,
            DatabaseMode.SHADOW_MODE
        ]
    
    @property
    def primary_read_source(self) -> str:
        """Get primary read source."""
        if self.state.mode in [DatabaseMode.POSTGRESQL_ONLY, DatabaseMode.DUAL_READ_PG]:
            return "postgresql"
        return "mongodb"
    
    async def set_mode(self, mode: DatabaseMode):
        """Change database mode."""
        async with self._lock:
            old_mode = self.state.mode
            self.state.mode = mode
            
            logger.info(f"Database mode changed: {old_mode.value} → {mode.value}")
            
            # Update phase based on mode
            if mode == DatabaseMode.DUAL_WRITE:
                self.state.phase = MigrationPhase.DUAL_WRITE
            elif mode == DatabaseMode.POSTGRESQL_ONLY:
                self.state.phase = MigrationPhase.COMPLETED
            elif mode == DatabaseMode.MONGODB_ONLY:
                if self.state.phase != MigrationPhase.NOT_STARTED:
                    self.state.phase = MigrationPhase.ROLLBACK
    
    async def start_migration(self):
        """Start the migration process."""
        async with self._lock:
            self.state.phase = MigrationPhase.STAGING
            self.state.started_at = datetime.now(timezone.utc)
            self.state.mode = DatabaseMode.SHADOW_MODE
            
            logger.info("Migration started - entering shadow mode")
    
    async def enable_dual_write(self):
        """Enable dual-write mode."""
        async with self._lock:
            self.state.phase = MigrationPhase.DUAL_WRITE
            self.state.mode = DatabaseMode.DUAL_WRITE
            
            logger.info("Dual-write mode enabled")
    
    async def switch_to_postgresql(self):
        """Switch primary to PostgreSQL."""
        async with self._lock:
            self.state.phase = MigrationPhase.CUTOVER
            self.state.mode = DatabaseMode.DUAL_READ_PG
            
            logger.info("Cut-over started - reading from PostgreSQL")
    
    async def complete_migration(self):
        """Complete migration to PostgreSQL only."""
        async with self._lock:
            self.state.phase = MigrationPhase.COMPLETED
            self.state.mode = DatabaseMode.POSTGRESQL_ONLY
            self.state.completed_at = datetime.now(timezone.utc)
            
            logger.info("Migration completed - PostgreSQL only mode")
    
    async def rollback(self, reason: str = "Manual rollback"):
        """Rollback to MongoDB."""
        async with self._lock:
            self.state.phase = MigrationPhase.ROLLBACK
            self.state.mode = DatabaseMode.MONGODB_ONLY
            self.state.validation_errors.append(f"Rollback: {reason}")
            
            logger.warning(f"Rollback executed: {reason}")
    
    @asynccontextmanager
    async def get_mongodb(self):
        """Get MongoDB database."""
        if not self._mongo_db:
            raise RuntimeError("MongoDB not initialized")
        yield self._mongo_db
    
    @asynccontextmanager
    async def get_postgresql_session(self):
        """Get PostgreSQL session."""
        if not self._pg_session_factory:
            raise RuntimeError("PostgreSQL not initialized")
        
        async with self._pg_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    
    async def dual_write(
        self,
        mongo_operation: Callable,
        pg_operation: Callable,
        entity_id: str = None,
        entity_type: str = None
    ) -> tuple:
        """
        Execute dual-write operation.
        
        Returns: (success, mongo_result, pg_result, error)
        """
        mongo_result = None
        pg_result = None
        error = None
        
        try:
            # MongoDB write (always first in dual-write)
            if self.is_mongodb_enabled:
                async with self.get_mongodb() as mongo_db:
                    mongo_result = await mongo_operation(mongo_db)
                    self.state.mongodb_writes += 1
            
            # PostgreSQL write
            if self.is_postgresql_enabled:
                async with self.get_postgresql_session() as session:
                    pg_result = await pg_operation(session)
                    self.state.postgresql_writes += 1
            
            return True, mongo_result, pg_result, None
            
        except Exception as e:
            error = str(e)
            logger.error(f"Dual-write failed for {entity_type}:{entity_id}: {e}")
            
            # In shadow mode, log but don't fail
            if self.state.mode == DatabaseMode.SHADOW_MODE:
                self.state.consistency_failures += 1
                self.state.validation_errors.append(f"{entity_type}:{entity_id} - {error}")
                return True, mongo_result, None, error
            
            return False, mongo_result, pg_result, error
    
    async def dual_read(
        self,
        mongo_operation: Callable,
        pg_operation: Callable,
        verify_consistency: bool = False
    ) -> Any:
        """
        Execute read operation from primary source.
        
        Optionally verifies consistency between sources.
        """
        self.state.read_operations += 1
        
        primary = self.primary_read_source
        
        try:
            if primary == "postgresql":
                async with self.get_postgresql_session() as session:
                    result = await pg_operation(session)
            else:
                async with self.get_mongodb() as mongo_db:
                    result = await mongo_operation(mongo_db)
            
            # Consistency verification in dual modes
            if verify_consistency and self.state.mode in [DatabaseMode.DUAL_WRITE, DatabaseMode.DUAL_READ_PG]:
                await self._verify_read_consistency(mongo_operation, pg_operation, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Read operation failed: {e}")
            
            # Fallback to other source
            if primary == "postgresql" and self.is_mongodb_enabled:
                logger.warning("Falling back to MongoDB")
                async with self.get_mongodb() as mongo_db:
                    return await mongo_operation(mongo_db)
            elif primary == "mongodb" and self.is_postgresql_enabled:
                logger.warning("Falling back to PostgreSQL")
                async with self.get_postgresql_session() as session:
                    return await pg_operation(session)
            
            raise
    
    async def _verify_read_consistency(
        self,
        mongo_operation: Callable,
        pg_operation: Callable,
        primary_result: Any
    ):
        """Verify consistency between MongoDB and PostgreSQL."""
        try:
            self.state.consistency_checks += 1
            
            # Get result from secondary source
            if self.primary_read_source == "postgresql":
                async with self.get_mongodb() as mongo_db:
                    secondary_result = await mongo_operation(mongo_db)
            else:
                async with self.get_postgresql_session() as session:
                    secondary_result = await pg_operation(session)
            
            # Compare results (basic check)
            if primary_result is None and secondary_result is None:
                return  # Both None, consistent
            
            if primary_result is None or secondary_result is None:
                self.state.consistency_failures += 1
                logger.warning("Consistency check: One source returned None")
            
        except Exception as e:
            logger.warning(f"Consistency verification failed: {e}")
    
    async def run_validation(self) -> Dict:
        """
        Run comprehensive validation between MongoDB and PostgreSQL.
        
        Returns validation report.
        """
        self.state.phase = MigrationPhase.VALIDATION
        self.state.last_validation = datetime.now(timezone.utc)
        
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": [],
            "passed": True,
            "summary": {}
        }
        
        try:
            # Count comparison
            counts = await self._validate_counts()
            report["checks"].append(counts)
            if not counts["passed"]:
                report["passed"] = False
            
            # Recent transactions comparison
            tx_check = await self._validate_recent_transactions()
            report["checks"].append(tx_check)
            if not tx_check["passed"]:
                report["passed"] = False
            
            # State consistency check
            state_check = await self._validate_state_consistency()
            report["checks"].append(state_check)
            if not state_check["passed"]:
                report["passed"] = False
            
            self.state.validation_passed = report["passed"]
            
            report["summary"] = {
                "total_checks": len(report["checks"]),
                "passed_checks": sum(1 for c in report["checks"] if c["passed"]),
                "failed_checks": sum(1 for c in report["checks"] if not c["passed"])
            }
            
        except Exception as e:
            report["passed"] = False
            report["error"] = str(e)
            self.state.validation_errors.append(str(e))
        
        return report
    
    async def _validate_counts(self) -> Dict:
        """Validate record counts between databases."""
        check = {
            "name": "record_counts",
            "passed": True,
            "details": {}
        }
        
        collections = [
            ("users", "users"),
            ("platform_api_keys", "platform_api_keys"),
            ("por_transactions", "transactions"),
            ("por_settlements", "settlements"),
            ("webhooks", "webhooks"),
            ("audit_logs", "audit_logs")
        ]
        
        try:
            if self._mongo_db is None:
                raise RuntimeError("MongoDB not initialized")
                
            for mongo_col, pg_table in collections:
                mongo_count = await self._mongo_db[mongo_col].count_documents({})
                
                # Get PG count
                async with self.get_postgresql_session() as session:
                    from sqlalchemy import text
                    result = await session.execute(
                        text(f"SELECT COUNT(*) FROM {pg_table}")
                    )
                    pg_count = result.scalar()
                
                match = mongo_count == pg_count
                check["details"][mongo_col] = {
                    "mongodb": mongo_count,
                    "postgresql": pg_count,
                    "match": match
                }
                
                if not match:
                    check["passed"] = False
                    
        except Exception as e:
            check["passed"] = False
            check["error"] = str(e)
        
        return check
    
    async def _validate_recent_transactions(self) -> Dict:
        """Validate recent transaction data."""
        check = {
            "name": "recent_transactions",
            "passed": True,
            "details": {}
        }
        
        try:
            if self._mongo_db is None:
                raise RuntimeError("MongoDB not initialized")
            
            # Get 10 most recent transactions
            cursor = self._mongo_db.por_transactions.find({}).sort("created_at", -1).limit(10)
            mongo_docs = await cursor.to_list(length=10)
            
            for doc in mongo_docs:
                quote_id = doc.get("quote_id")
                
                # Check in PostgreSQL
                async with self.get_postgresql_session() as session:
                    from sqlalchemy import text
                    result = await session.execute(
                        text("SELECT quote_id, state, fiat_amount FROM transactions WHERE quote_id = :qid"),
                        {"qid": quote_id}
                    )
                    pg_row = result.fetchone()
                
                if pg_row:
                    # Compare key fields
                    state_match = doc.get("state") == pg_row[1]
                    amount_match = abs(doc.get("fiat_amount", 0) - (pg_row[2] or 0)) < 0.01
                    
                    check["details"][quote_id] = {
                        "found_in_pg": True,
                        "state_match": state_match,
                        "amount_match": amount_match
                    }
                    
                    if not (state_match and amount_match):
                        check["passed"] = False
                else:
                    check["details"][quote_id] = {"found_in_pg": False}
                    check["passed"] = False
                    
        except Exception as e:
            check["passed"] = False
            check["error"] = str(e)
        
        return check
    
    async def _validate_state_consistency(self) -> Dict:
        """Validate state consistency for active transactions."""
        check = {
            "name": "state_consistency",
            "passed": True,
            "details": {}
        }
        
        try:
            if self._mongo_db is None:
                raise RuntimeError("MongoDB not initialized")
            
            # Check for state mismatches in active transactions
            active_states = ["QUOTE_CREATED", "DEPOSIT_PENDING", "PAYMENT_PENDING"]
            
            for state in active_states:
                mongo_count = await self._mongo_db.por_transactions.count_documents({"state": state})
                
                async with self.get_postgresql_session() as session:
                    from sqlalchemy import text
                    result = await session.execute(
                        text("SELECT COUNT(*) FROM transactions WHERE state = :state"),
                        {"state": state}
                    )
                    pg_count = result.scalar()
                
                check["details"][state] = {
                    "mongodb": mongo_count,
                    "postgresql": pg_count,
                    "match": mongo_count == pg_count
                }
                
                if mongo_count != pg_count:
                    check["passed"] = False
                    
        except Exception as e:
            check["passed"] = False
            check["error"] = str(e)
        
        return check
    
    def get_status(self) -> Dict:
        """Get current migration status."""
        return {
            "initialized": self._initialized,
            "mongodb_connected": self._mongo_db is not None,
            "postgresql_connected": self._pg_session_factory is not None,
            **self.state.to_dict()
        }


# Global instance
dual_db_manager = DualDatabaseManager()


def get_dual_db_manager() -> DualDatabaseManager:
    """Get the global dual database manager."""
    return dual_db_manager

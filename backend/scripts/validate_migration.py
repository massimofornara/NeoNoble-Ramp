"""
PostgreSQL Migration Validation Script.

Comprehensive validation for the PostgreSQL migration including:
- Data integrity checks
- Lifecycle consistency verification
- Performance benchmarking
- E2E flow validation

Usage:
    python -m scripts.validate_migration --full
    python -m scripts.validate_migration --quick
    python -m scripts.validate_migration --lifecycle
"""

import asyncio
import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Any

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MigrationValidator:
    """Comprehensive migration validation."""
    
    def __init__(self):
        # MongoDB
        self.mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        self.mongo_db_name = os.environ.get("DB_NAME", "neonoble_ramp")
        self.mongo_client = None
        self.mongo_db = None
        
        # PostgreSQL
        pg_host = os.environ.get("POSTGRES_HOST", "localhost")
        pg_port = os.environ.get("POSTGRES_PORT", "5432")
        pg_user = os.environ.get("POSTGRES_USER", "neonoble")
        pg_password = os.environ.get("POSTGRES_PASSWORD", "neonoble_secret")
        pg_database = os.environ.get("POSTGRES_DB", "neonoble_ramp")
        
        self.pg_url = f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
        self.pg_engine = None
        self.pg_session_factory = None
        
        self.results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": [],
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "warnings": 0
            }
        }
    
    async def connect(self):
        """Establish connections."""
        logger.info("Connecting to databases...")
        
        try:
            self.mongo_client = AsyncIOMotorClient(self.mongo_url)
            self.mongo_db = self.mongo_client[self.mongo_db_name]
            await self.mongo_db.command("ping")
            logger.info("✓ MongoDB connected")
        except Exception as e:
            logger.error(f"✗ MongoDB connection failed: {e}")
            raise
        
        try:
            self.pg_engine = create_async_engine(self.pg_url, echo=False)
            self.pg_session_factory = async_sessionmaker(
                self.pg_engine, class_=AsyncSession, expire_on_commit=False
            )
            async with self.pg_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("✓ PostgreSQL connected")
        except Exception as e:
            logger.error(f"✗ PostgreSQL connection failed: {e}")
            raise
    
    async def disconnect(self):
        """Close connections."""
        if self.mongo_client:
            self.mongo_client.close()
        if self.pg_engine:
            await self.pg_engine.dispose()
    
    def add_result(self, name: str, passed: bool, details: Dict = None, warning: bool = False):
        """Add validation result."""
        status = "PASSED" if passed else ("WARNING" if warning else "FAILED")
        self.results["checks"].append({
            "name": name,
            "status": status,
            "details": details or {}
        })
        
        self.results["summary"]["total"] += 1
        if passed:
            self.results["summary"]["passed"] += 1
        elif warning:
            self.results["summary"]["warnings"] += 1
        else:
            self.results["summary"]["failed"] += 1
        
        icon = "✓" if passed else ("⚠" if warning else "✗")
        logger.info(f"{icon} {name}: {status}")
    
    # ========================
    # Data Integrity Checks
    # ========================
    
    async def check_record_counts(self):
        """Compare record counts between databases."""
        logger.info("\n=== Record Count Validation ===")
        
        collections = [
            ("users", "users"),
            ("platform_api_keys", "platform_api_keys"),
            ("por_transactions", "transactions"),
            ("por_settlements", "settlements"),
            ("webhooks", "webhooks"),
            ("webhook_deliveries", "webhook_deliveries"),
            ("audit_logs", "audit_logs")
        ]
        
        for mongo_col, pg_table in collections:
            try:
                mongo_count = await self.mongo_db[mongo_col].count_documents({})
                
                async with self.pg_session_factory() as session:
                    result = await session.execute(text(f"SELECT COUNT(*) FROM {pg_table}"))
                    pg_count = result.scalar() or 0
                
                match = mongo_count == pg_count
                self.add_result(
                    f"count_{mongo_col}",
                    match,
                    {"mongodb": mongo_count, "postgresql": pg_count},
                    warning=(mongo_count > pg_count)
                )
                
            except Exception as e:
                self.add_result(f"count_{mongo_col}", False, {"error": str(e)})
    
    async def check_user_integrity(self):
        """Verify user data integrity."""
        logger.info("\n=== User Data Integrity ===")
        
        try:
            cursor = self.mongo_db.users.find({}).limit(100)
            mongo_users = await cursor.to_list(length=100)
            
            mismatches = []
            for user in mongo_users:
                email = user.get("email")
                
                async with self.pg_session_factory() as session:
                    result = await session.execute(
                        text("SELECT id, email, role FROM users WHERE email = :email"),
                        {"email": email}
                    )
                    pg_user = result.fetchone()
                
                if not pg_user:
                    mismatches.append({"email": email, "issue": "missing_in_pg"})
                elif user.get("role") != pg_user[2]:
                    mismatches.append({"email": email, "issue": "role_mismatch"})
            
            self.add_result(
                "user_integrity",
                len(mismatches) == 0,
                {"checked": len(mongo_users), "mismatches": mismatches[:10]}
            )
            
        except Exception as e:
            self.add_result("user_integrity", False, {"error": str(e)})
    
    async def check_transaction_integrity(self):
        """Verify transaction data integrity."""
        logger.info("\n=== Transaction Data Integrity ===")
        
        try:
            cursor = self.mongo_db.por_transactions.find({}).sort("created_at", -1).limit(100)
            mongo_txs = await cursor.to_list(length=100)
            
            mismatches = []
            for tx in mongo_txs:
                quote_id = tx.get("quote_id")
                
                async with self.pg_session_factory() as session:
                    result = await session.execute(
                        text("""
                            SELECT quote_id, state, crypto_amount, fiat_amount, 
                                   fee_amount, exchange_rate, direction
                            FROM transactions WHERE quote_id = :qid
                        """),
                        {"qid": quote_id}
                    )
                    pg_tx = result.fetchone()
                
                if not pg_tx:
                    mismatches.append({"quote_id": quote_id, "issue": "missing_in_pg"})
                else:
                    issues = []
                    if tx.get("state") != pg_tx[1]:
                        issues.append(f"state: {tx.get('state')} vs {pg_tx[1]}")
                    if abs(tx.get("crypto_amount", 0) - (pg_tx[2] or 0)) > 0.0001:
                        issues.append("crypto_amount")
                    if abs(tx.get("fiat_amount", 0) - (pg_tx[3] or 0)) > 0.01:
                        issues.append("fiat_amount")
                    if issues:
                        mismatches.append({"quote_id": quote_id, "issues": issues})
            
            self.add_result(
                "transaction_integrity",
                len(mismatches) == 0,
                {"checked": len(mongo_txs), "mismatches": mismatches[:10]}
            )
            
        except Exception as e:
            self.add_result("transaction_integrity", False, {"error": str(e)})
    
    async def check_timeline_integrity(self):
        """Verify timeline event integrity."""
        logger.info("\n=== Timeline Event Integrity ===")
        
        try:
            # Get transactions with timelines
            cursor = self.mongo_db.por_transactions.find(
                {"timeline": {"$exists": True, "$ne": []}}
            ).limit(50)
            mongo_txs = await cursor.to_list(length=50)
            
            mismatches = []
            for tx in mongo_txs:
                quote_id = tx.get("quote_id")
                mongo_timeline_count = len(tx.get("timeline", []))
                
                async with self.pg_session_factory() as session:
                    result = await session.execute(
                        text("""
                            SELECT COUNT(*) FROM timeline_events te
                            JOIN transactions t ON te.transaction_id = t.id
                            WHERE t.quote_id = :qid
                        """),
                        {"qid": quote_id}
                    )
                    pg_count = result.scalar() or 0
                
                if mongo_timeline_count != pg_count:
                    mismatches.append({
                        "quote_id": quote_id,
                        "mongo_events": mongo_timeline_count,
                        "pg_events": pg_count
                    })
            
            self.add_result(
                "timeline_integrity",
                len(mismatches) == 0,
                {"checked": len(mongo_txs), "mismatches": mismatches[:10]}
            )
            
        except Exception as e:
            self.add_result("timeline_integrity", False, {"error": str(e)})
    
    # ========================
    # Lifecycle Consistency
    # ========================
    
    async def check_state_consistency(self):
        """Verify state consistency across databases."""
        logger.info("\n=== State Consistency ===")
        
        states = [
            "QUOTE_CREATED", "QUOTE_ACCEPTED", "DEPOSIT_PENDING", "DEPOSIT_DETECTED",
            "DEPOSIT_CONFIRMED", "PAYMENT_PENDING", "PAYMENT_DETECTED", "PAYMENT_CONFIRMED",
            "SETTLEMENT_PENDING", "COMPLETED", "FAILED"
        ]
        
        mismatches = []
        for state in states:
            try:
                mongo_count = await self.mongo_db.por_transactions.count_documents({"state": state})
                
                async with self.pg_session_factory() as session:
                    result = await session.execute(
                        text("SELECT COUNT(*) FROM transactions WHERE state = :state"),
                        {"state": state}
                    )
                    pg_count = result.scalar() or 0
                
                if mongo_count != pg_count:
                    mismatches.append({
                        "state": state,
                        "mongodb": mongo_count,
                        "postgresql": pg_count
                    })
                    
            except Exception as e:
                mismatches.append({"state": state, "error": str(e)})
        
        self.add_result(
            "state_consistency",
            len(mismatches) == 0,
            {"states_checked": len(states), "mismatches": mismatches}
        )
    
    async def check_direction_consistency(self):
        """Verify on-ramp/off-ramp direction consistency."""
        logger.info("\n=== Direction Consistency ===")
        
        try:
            # MongoDB - count by direction
            mongo_onramp = await self.mongo_db.por_transactions.count_documents(
                {"$or": [{"direction": "onramp"}, {"metadata.direction": "onramp"}]}
            )
            mongo_offramp = await self.mongo_db.por_transactions.count_documents(
                {"$or": [{"direction": "offramp"}, {"metadata.direction": "offramp"}, {"direction": {"$exists": False}}]}
            )
            
            async with self.pg_session_factory() as session:
                result = await session.execute(
                    text("SELECT direction, COUNT(*) FROM transactions GROUP BY direction")
                )
                pg_counts = dict(result.fetchall())
            
            pg_onramp = pg_counts.get("onramp", 0)
            pg_offramp = pg_counts.get("offramp", 0)
            
            self.add_result(
                "direction_consistency",
                True,  # Informational
                {
                    "mongodb": {"onramp": mongo_onramp, "offramp": mongo_offramp},
                    "postgresql": {"onramp": pg_onramp, "offramp": pg_offramp}
                }
            )
            
        except Exception as e:
            self.add_result("direction_consistency", False, {"error": str(e)})
    
    # ========================
    # Performance Benchmarks
    # ========================
    
    async def benchmark_read_performance(self):
        """Benchmark read performance."""
        logger.info("\n=== Read Performance Benchmark ===")
        
        try:
            # MongoDB read
            start = time.time()
            for _ in range(100):
                await self.mongo_db.por_transactions.find_one({"state": "COMPLETED"})
            mongo_time = (time.time() - start) * 10  # ms per operation
            
            # PostgreSQL read
            start = time.time()
            for _ in range(100):
                async with self.pg_session_factory() as session:
                    await session.execute(
                        text("SELECT * FROM transactions WHERE state = 'COMPLETED' LIMIT 1")
                    )
            pg_time = (time.time() - start) * 10  # ms per operation
            
            self.add_result(
                "read_performance",
                True,
                {
                    "mongodb_avg_ms": round(mongo_time, 2),
                    "postgresql_avg_ms": round(pg_time, 2),
                    "operations": 100
                }
            )
            
        except Exception as e:
            self.add_result("read_performance", False, {"error": str(e)})
    
    async def benchmark_query_performance(self):
        """Benchmark complex query performance."""
        logger.info("\n=== Query Performance Benchmark ===")
        
        try:
            # MongoDB aggregation
            start = time.time()
            pipeline = [
                {"$match": {"state": "COMPLETED"}},
                {"$group": {"_id": "$crypto_currency", "total": {"$sum": "$fiat_amount"}}},
                {"$sort": {"total": -1}}
            ]
            await self.mongo_db.por_transactions.aggregate(pipeline).to_list(length=10)
            mongo_time = (time.time() - start) * 1000
            
            # PostgreSQL query
            start = time.time()
            async with self.pg_session_factory() as session:
                await session.execute(text("""
                    SELECT crypto_currency, SUM(fiat_amount) as total
                    FROM transactions WHERE state = 'COMPLETED'
                    GROUP BY crypto_currency
                    ORDER BY total DESC
                    LIMIT 10
                """))
            pg_time = (time.time() - start) * 1000
            
            self.add_result(
                "query_performance",
                True,
                {
                    "mongodb_ms": round(mongo_time, 2),
                    "postgresql_ms": round(pg_time, 2),
                    "query_type": "aggregation"
                }
            )
            
        except Exception as e:
            self.add_result("query_performance", False, {"error": str(e)})
    
    # ========================
    # Run Validation
    # ========================
    
    async def run_quick(self):
        """Run quick validation."""
        await self.check_record_counts()
        await self.check_state_consistency()
    
    async def run_lifecycle(self):
        """Run lifecycle-focused validation."""
        await self.check_state_consistency()
        await self.check_direction_consistency()
        await self.check_timeline_integrity()
    
    async def run_full(self):
        """Run full validation."""
        await self.check_record_counts()
        await self.check_user_integrity()
        await self.check_transaction_integrity()
        await self.check_timeline_integrity()
        await self.check_state_consistency()
        await self.check_direction_consistency()
        await self.benchmark_read_performance()
        await self.benchmark_query_performance()
    
    def print_report(self):
        """Print validation report."""
        print("\n" + "=" * 60)
        print("MIGRATION VALIDATION REPORT")
        print("=" * 60)
        print(f"Timestamp: {self.results['timestamp']}")
        print("\nSummary:")
        print(f"  Total Checks: {self.results['summary']['total']}")
        print(f"  Passed: {self.results['summary']['passed']}")
        print(f"  Failed: {self.results['summary']['failed']}")
        print(f"  Warnings: {self.results['summary']['warnings']}")
        
        if self.results['summary']['failed'] > 0:
            print("\n❌ VALIDATION FAILED")
            print("Failed checks:")
            for check in self.results['checks']:
                if check['status'] == 'FAILED':
                    print(f"  - {check['name']}: {check.get('details', {})}")
        else:
            print("\n✅ VALIDATION PASSED")
        
        print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description="Validate PostgreSQL migration")
    parser.add_argument("--quick", action="store_true", help="Quick validation")
    parser.add_argument("--lifecycle", action="store_true", help="Lifecycle validation")
    parser.add_argument("--full", action="store_true", default=True, help="Full validation")
    
    args = parser.parse_args()
    
    validator = MigrationValidator()
    
    try:
        await validator.connect()
        
        if args.quick:
            await validator.run_quick()
        elif args.lifecycle:
            await validator.run_lifecycle()
        else:
            await validator.run_full()
        
        validator.print_report()
        
    finally:
        await validator.disconnect()
    
    # Exit with error code if validation failed
    sys.exit(0 if validator.results['summary']['failed'] == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())

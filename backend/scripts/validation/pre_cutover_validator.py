"""
Pre-Cutover Validation Script.

Runs comprehensive validation checks before authorizing final PostgreSQL cutover.
Designed to be run repeatedly during the validation phase.

Usage:
    python -m scripts.validation.pre_cutover_validator
"""

import asyncio
import os
import sys
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from motor.motor_asyncio import AsyncIOMotorClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PreCutoverValidator:
    """Comprehensive pre-cutover validation."""
    
    def __init__(self):
        # MongoDB
        self.mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        self.mongo_db_name = os.environ.get("DB_NAME", "neonoble_ramp")
        self.mongo_client = None
        self.mongo_db = None
        
        # PostgreSQL
        pg_host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
        pg_port = os.environ.get("POSTGRES_PORT", "5432")
        pg_user = os.environ.get("POSTGRES_USER", "neonoble")
        pg_password = os.environ.get("POSTGRES_PASSWORD", "neonoble_secret_2025")
        pg_database = os.environ.get("POSTGRES_DB", "neonoble_ramp")
        
        self.pg_url = f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
        self.pg_engine = None
        self.pg_session_factory = None
        
        self.results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": [],
            "passed": True,
            "ready_for_cutover": False
        }
    
    async def connect(self):
        """Connect to databases."""
        self.mongo_client = AsyncIOMotorClient(self.mongo_url)
        self.mongo_db = self.mongo_client[self.mongo_db_name]
        
        self.pg_engine = create_async_engine(self.pg_url, echo=False)
        self.pg_session_factory = async_sessionmaker(
            self.pg_engine, class_=AsyncSession, expire_on_commit=False
        )
        logger.info("Connected to both databases")
    
    async def disconnect(self):
        """Close connections."""
        if self.mongo_client:
            self.mongo_client.close()
        if self.pg_engine:
            await self.pg_engine.dispose()
    
    def add_check(self, name: str, passed: bool, details: Dict = None, error: str = None):
        """Add check result."""
        check = {
            "name": name,
            "passed": passed,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        if error:
            check["error"] = error
        self.results["checks"].append(check)
        if not passed:
            self.results["passed"] = False
        
        status = "✅" if passed else "❌"
        logger.info(f"{status} {name}")
    
    async def check_record_counts(self):
        """Validate record counts match."""
        collections = [
            ("users", "users"),
            ("platform_api_keys", "platform_api_keys"),
            ("por_transactions", "transactions"),
            ("por_settlements", "settlements"),
            ("webhooks", "webhooks"),
            ("audit_logs", "audit_logs")
        ]
        
        details = {}
        all_match = True
        
        for mongo_col, pg_table in collections:
            mongo_count = await self.mongo_db[mongo_col].count_documents({})
            
            async with self.pg_session_factory() as session:
                result = await session.execute(text(f"SELECT COUNT(*) FROM {pg_table}"))
                pg_count = result.scalar()
            
            # Allow 2 record difference for legacy system API keys
            tolerance = 2 if mongo_col == "platform_api_keys" else 0
            match = abs(mongo_count - pg_count) <= tolerance
            
            details[mongo_col] = {
                "mongodb": mongo_count,
                "postgresql": pg_count,
                "match": match,
                "tolerance": tolerance
            }
            
            if not match:
                all_match = False
        
        self.add_check("record_counts", all_match, details)
    
    async def check_recent_transactions(self):
        """Validate recent transactions exist in both databases."""
        cursor = self.mongo_db.por_transactions.find({}).sort("created_at", -1).limit(20)
        mongo_docs = await cursor.to_list(length=20)
        
        details = {}
        all_found = True
        
        for doc in mongo_docs:
            quote_id = doc.get("quote_id")
            
            async with self.pg_session_factory() as session:
                result = await session.execute(
                    text("SELECT quote_id, state, fiat_amount, crypto_amount FROM transactions WHERE quote_id = :qid"),
                    {"qid": quote_id}
                )
                pg_row = result.fetchone()
            
            if pg_row:
                state_match = doc.get("state") == pg_row[1]
                fiat_match = abs(doc.get("fiat_amount", 0) - (pg_row[2] or 0)) < 0.01
                crypto_match = abs(doc.get("crypto_amount", 0) - (pg_row[3] or 0)) < 0.0001
                
                details[quote_id] = {
                    "found": True,
                    "state_match": state_match,
                    "fiat_match": fiat_match,
                    "crypto_match": crypto_match
                }
                
                if not (state_match and fiat_match and crypto_match):
                    all_found = False
            else:
                details[quote_id] = {"found": False}
                all_found = False
        
        self.add_check("recent_transactions", all_found, details)
    
    async def check_timeline_integrity(self):
        """Validate timeline events are properly ordered."""
        # Get 10 recent completed transactions
        cursor = self.mongo_db.por_transactions.find(
            {"state": "COMPLETED"}
        ).sort("created_at", -1).limit(10)
        mongo_docs = await cursor.to_list(length=10)
        
        details = {}
        all_valid = True
        
        for doc in mongo_docs:
            quote_id = doc.get("quote_id")
            mongo_timeline = doc.get("timeline", [])
            
            # Get PostgreSQL timeline
            async with self.pg_session_factory() as session:
                # First get transaction ID
                tx_result = await session.execute(
                    text("SELECT id FROM transactions WHERE quote_id = :qid"),
                    {"qid": quote_id}
                )
                tx_row = tx_result.fetchone()
                
                if tx_row:
                    # Get timeline events
                    timeline_result = await session.execute(
                        text("SELECT state, created_at FROM timeline_events WHERE transaction_id = :tid ORDER BY created_at"),
                        {"tid": tx_row[0]}
                    )
                    pg_timeline = timeline_result.fetchall()
                    
                    # Check count and order
                    count_match = len(mongo_timeline) == len(pg_timeline)
                    
                    # Check timestamps are monotonically increasing
                    timestamps_ordered = True
                    prev_ts = None
                    for row in pg_timeline:
                        if prev_ts and row[1] < prev_ts:
                            timestamps_ordered = False
                            break
                        prev_ts = row[1]
                    
                    details[quote_id] = {
                        "mongo_events": len(mongo_timeline),
                        "pg_events": len(pg_timeline),
                        "count_match": count_match,
                        "timestamps_ordered": timestamps_ordered
                    }
                    
                    if not (count_match and timestamps_ordered):
                        all_valid = False
                else:
                    details[quote_id] = {"found": False}
                    all_valid = False
        
        self.add_check("timeline_integrity", all_valid, details)
    
    async def check_settlement_consistency(self):
        """Validate settlement amounts and status."""
        cursor = self.mongo_db.por_settlements.find({}).sort("created_at", -1).limit(20)
        mongo_docs = await cursor.to_list(length=20)
        
        details = {}
        all_consistent = True
        
        for doc in mongo_docs:
            settlement_id = doc.get("settlement_id")
            mongo_amount = doc.get("amount") or doc.get("amount_eur", 0)
            
            async with self.pg_session_factory() as session:
                result = await session.execute(
                    text("SELECT settlement_id, amount, status FROM settlements WHERE settlement_id = :sid"),
                    {"sid": settlement_id}
                )
                pg_row = result.fetchone()
            
            if pg_row:
                amount_match = abs(mongo_amount - (pg_row[1] or 0)) < 0.01
                status_match = doc.get("status") == pg_row[2]
                
                details[settlement_id] = {
                    "found": True,
                    "amount_match": amount_match,
                    "status_match": status_match,
                    "mongo_amount": mongo_amount,
                    "pg_amount": pg_row[1]
                }
                
                if not (amount_match and status_match):
                    all_consistent = False
            else:
                details[settlement_id] = {"found": False}
                all_consistent = False
        
        self.add_check("settlement_consistency", all_consistent, details)
    
    async def check_audit_completeness(self):
        """Validate audit log completeness."""
        # Count audit logs
        mongo_count = await self.mongo_db.audit_logs.count_documents({})
        
        async with self.pg_session_factory() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM audit_logs"))
            pg_count = result.scalar()
        
        match = mongo_count == pg_count
        
        details = {
            "mongodb": mongo_count,
            "postgresql": pg_count,
            "match": match
        }
        
        self.add_check("audit_completeness", match, details)
    
    async def check_utc_timestamps(self):
        """Validate timestamps are UTC-normalized."""
        # Sample transactions from PostgreSQL
        async with self.pg_session_factory() as session:
            result = await session.execute(
                text("SELECT quote_id, created_at, expires_at FROM transactions LIMIT 10")
            )
            rows = result.fetchall()
        
        all_utc = True
        details = {}
        
        for row in rows:
            quote_id = row[0]
            created_at = row[1]
            expires_at = row[2]
            
            # Check if timestamps have timezone info
            created_tz = created_at.tzinfo is not None if created_at else True
            expires_tz = expires_at.tzinfo is not None if expires_at else True
            
            details[quote_id] = {
                "created_at_has_tz": created_tz,
                "expires_at_has_tz": expires_tz
            }
            
            if not (created_tz and expires_tz):
                all_utc = False
        
        self.add_check("utc_timestamps", all_utc, details)
    
    async def check_webhook_health(self):
        """Validate webhook configuration."""
        mongo_count = await self.mongo_db.webhooks.count_documents({})
        
        async with self.pg_session_factory() as session:
            result = await session.execute(
                text("SELECT COUNT(*), COUNT(*) FILTER (WHERE enabled = true) FROM webhooks")
            )
            row = result.fetchone()
            pg_count = row[0]
            enabled_count = row[1]
        
        match = mongo_count == pg_count
        
        details = {
            "mongodb": mongo_count,
            "postgresql": pg_count,
            "enabled": enabled_count,
            "match": match
        }
        
        self.add_check("webhook_health", match, details)
    
    async def run_all_checks(self):
        """Run all validation checks."""
        logger.info("="*60)
        logger.info("PRE-CUTOVER VALIDATION")
        logger.info("="*60)
        
        await self.connect()
        
        try:
            await self.check_record_counts()
            await self.check_recent_transactions()
            await self.check_timeline_integrity()
            await self.check_settlement_consistency()
            await self.check_audit_completeness()
            await self.check_utc_timestamps()
            await self.check_webhook_health()
        finally:
            await self.disconnect()
        
        # Determine cutover readiness
        passed_checks = sum(1 for c in self.results["checks"] if c["passed"])
        total_checks = len(self.results["checks"])
        
        self.results["summary"] = {
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": total_checks - passed_checks,
            "pass_rate": f"{(passed_checks/total_checks)*100:.1f}%"
        }
        
        # Ready for cutover if all checks pass
        self.results["ready_for_cutover"] = self.results["passed"]
        
        logger.info("="*60)
        logger.info(f"VALIDATION SUMMARY: {passed_checks}/{total_checks} checks passed")
        logger.info(f"READY FOR CUTOVER: {self.results['ready_for_cutover']}")
        logger.info("="*60)
        
        return self.results


async def main():
    validator = PreCutoverValidator()
    results = await validator.run_all_checks()
    
    # Output JSON for parsing
    print("\n" + "="*60)
    print("VALIDATION RESULTS (JSON):")
    print("="*60)
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())

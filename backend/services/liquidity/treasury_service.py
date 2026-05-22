"""
Treasury Service.

Manages the PoR treasury liquidity pool including:
- Ledger operations (inflows, outflows, adjustments)
- Balance tracking (real + virtual floor)
- Coverage ratio monitoring
- Snapshot generation

This is the primary source of truth for treasury state.
"""

import os
import logging
import hashlib
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.liquidity.treasury_models import (
    LedgerEntryType,
    LedgerEntry,
    TreasurySnapshot,
    TreasuryConfig
)

logger = logging.getLogger(__name__)


class TreasuryService:
    """
    Treasury service for PoR liquidity management.
    
    Features:
    - Monotonic ledger sequencing
    - Real + virtual floor balance tracking
    - Coverage ratio monitoring
    - Deterministic snapshot generation
    - Audit-grade integrity verification
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.ledger_collection = db.treasury_ledger
        self.snapshots_collection = db.treasury_snapshots
        self.config_collection = db.treasury_config
        
        self._initialized = False
        self._config: Optional[TreasuryConfig] = None
        self._sequence_counter = 0
        self._last_entry_hash: Optional[str] = None
    
    async def initialize(self):
        """Initialize treasury service."""
        if self._initialized:
            return
        
        # Create indexes
        await self.ledger_collection.create_index("entry_id", unique=True)
        await self.ledger_collection.create_index("sequence_number", unique=True)
        await self.ledger_collection.create_index("quote_id")
        await self.ledger_collection.create_index("created_at")
        await self.ledger_collection.create_index("entry_type")
        await self.snapshots_collection.create_index("snapshot_id", unique=True)
        await self.snapshots_collection.create_index("timestamp")
        
        # Load or create config
        self._config = await self._load_or_create_config()
        
        # Initialize sequence counter
        last_entry = await self.ledger_collection.find_one(
            {}, sort=[("sequence_number", -1)]
        )
        if last_entry:
            self._sequence_counter = last_entry.get("sequence_number", 0)
            self._last_entry_hash = last_entry.get("audit_hash")
        else:
            # Create initial virtual floor entry
            await self._create_initial_floor_entry()
        
        self._initialized = True
        logger.info(
            f"Treasury Service initialized:\n"
            f"  Virtual Floor: €{self._config.virtual_floor_eur:,.2f}\n"
            f"  Base Currency: {self._config.base_currency}\n"
            f"  Last Sequence: {self._sequence_counter}"
        )
    
    async def _load_or_create_config(self) -> TreasuryConfig:
        """Load or create treasury configuration."""
        config_doc = await self.config_collection.find_one({"config_type": "treasury"})
        
        if config_doc:
            return TreasuryConfig(
                virtual_floor_eur=config_doc.get("virtual_floor_eur", 100_000_000.0),
                virtual_floor_enabled=config_doc.get("virtual_floor_enabled", True),
                initial_real_balance_eur=config_doc.get("initial_real_balance_eur", 0.0),
                min_coverage_ratio=config_doc.get("min_coverage_ratio", 1.0),
                target_coverage_ratio=config_doc.get("target_coverage_ratio", 1.5),
                critical_coverage_ratio=config_doc.get("critical_coverage_ratio", 0.8),
                supported_currencies=config_doc.get("supported_currencies", ["EUR", "NENO", "BNB", "USDT", "USDC"]),
                base_currency=config_doc.get("base_currency", "EUR"),
                auto_reconciliation_enabled=config_doc.get("auto_reconciliation_enabled", True),
                reconciliation_interval_hours=config_doc.get("reconciliation_interval_hours", 12)
            )
        
        # Create default config
        config = TreasuryConfig()
        await self.config_collection.insert_one({
            "config_type": "treasury",
            **config.to_dict(),
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        return config
    
    async def _create_initial_floor_entry(self):
        """Create initial virtual floor ledger entry."""
        await self.record_ledger_entry(
            entry_type=LedgerEntryType.VIRTUAL_FLOOR_CREDIT,
            amount=self._config.virtual_floor_eur,
            currency="EUR",
            description="Initial virtual floor liquidity",
            metadata={"initial_setup": True}
        )
        logger.info(f"Created initial virtual floor entry: €{self._config.virtual_floor_eur:,.2f}")
    
    def _generate_entry_hash(self, entry: LedgerEntry) -> str:
        """Generate audit hash for ledger entry."""
        hash_input = (
            f"{entry.entry_id}|{entry.sequence_number}|{entry.entry_type.value}|"
            f"{entry.amount}|{entry.currency}|{entry.balance_after}|"
            f"{entry.created_at}|{self._last_entry_hash or 'GENESIS'}"
        )
        return hashlib.sha256(hash_input.encode()).hexdigest()
    
    async def record_ledger_entry(
        self,
        entry_type: LedgerEntryType,
        amount: float,
        currency: str = "EUR",
        amount_eur_equivalent: Optional[float] = None,
        quote_id: Optional[str] = None,
        settlement_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        hedge_id: Optional[str] = None,
        conversion_id: Optional[str] = None,
        description: str = "",
        provider_reference: Optional[str] = None,
        rate_snapshot: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ) -> LedgerEntry:
        """
        Record a new treasury ledger entry.
        
        Maintains monotonic sequencing and chain integrity.
        """
        now = datetime.now(timezone.utc)
        
        # Get current balance
        current_balance = await self.get_balance(currency)
        
        # Determine if inflow or outflow
        is_inflow = entry_type in [
            LedgerEntryType.CRYPTO_INFLOW,
            LedgerEntryType.CRYPTO_CONVERSION,
            LedgerEntryType.HEDGE_SETTLEMENT,
            LedgerEntryType.TREASURY_DEPOSIT,
            LedgerEntryType.VIRTUAL_FLOOR_CREDIT,
            LedgerEntryType.FEE_ALLOCATION
        ]
        
        # Calculate signed amount
        signed_amount = abs(amount) if is_inflow else -abs(amount)
        new_balance = current_balance + signed_amount
        
        # Generate sequence number (atomic increment)
        self._sequence_counter += 1
        
        # EUR equivalent
        if amount_eur_equivalent is None:
            if currency == "EUR":
                amount_eur_equivalent = abs(amount)
            else:
                # Use rate snapshot or default rates
                rate = (rate_snapshot or {}).get(f"{currency}_EUR", 1.0)
                amount_eur_equivalent = abs(amount) * rate
        
        # Create entry
        entry = LedgerEntry(
            entry_id=f"led_{uuid4().hex[:12]}",
            sequence_number=self._sequence_counter,
            entry_type=entry_type,
            amount=signed_amount,
            currency=currency,
            amount_eur_equivalent=amount_eur_equivalent,
            balance_before=current_balance,
            balance_after=new_balance,
            quote_id=quote_id,
            settlement_id=settlement_id,
            batch_id=batch_id,
            hedge_id=hedge_id,
            conversion_id=conversion_id,
            description=description,
            provider_reference=provider_reference,
            rate_snapshot=rate_snapshot,
            created_at=now.isoformat(),
            effective_at=now.isoformat(),
            previous_entry_hash=self._last_entry_hash
        )
        
        # Generate audit hash
        entry.audit_hash = self._generate_entry_hash(entry)
        self._last_entry_hash = entry.audit_hash
        
        # Store in database
        await self.ledger_collection.insert_one(entry.to_dict())
        
        logger.info(
            f"Treasury Ledger Entry: {entry.entry_type.value} | "
            f"{'+'if signed_amount > 0 else ''}{signed_amount:,.2f} {currency} | "
            f"Balance: {new_balance:,.2f} {currency} | "
            f"Seq: {entry.sequence_number}"
        )
        
        return entry
    
    async def record_crypto_inflow(
        self,
        quote_id: str,
        crypto_amount: float,
        crypto_currency: str,
        eur_equivalent: float,
        tx_hash: Optional[str] = None
    ) -> LedgerEntry:
        """Record crypto deposit inflow."""
        return await self.record_ledger_entry(
            entry_type=LedgerEntryType.CRYPTO_INFLOW,
            amount=crypto_amount,
            currency=crypto_currency,
            amount_eur_equivalent=eur_equivalent,
            quote_id=quote_id,
            description=f"Crypto deposit: {crypto_amount} {crypto_currency}",
            provider_reference=tx_hash,
            rate_snapshot={f"{crypto_currency}_EUR": eur_equivalent / crypto_amount if crypto_amount > 0 else 0}
        )
    
    async def record_fiat_payout(
        self,
        quote_id: str,
        settlement_id: str,
        amount_eur: float,
        payout_reference: Optional[str] = None,
        payout_provider: str = "stripe"
    ) -> LedgerEntry:
        """Record fiat payout outflow."""
        return await self.record_ledger_entry(
            entry_type=LedgerEntryType.FIAT_PAYOUT,
            amount=amount_eur,
            currency="EUR",
            amount_eur_equivalent=amount_eur,
            quote_id=quote_id,
            settlement_id=settlement_id,
            description=f"SEPA payout: €{amount_eur:,.2f}",
            provider_reference=payout_reference,
            metadata={"provider": payout_provider}
        )
    
    async def record_fee_collection(
        self,
        quote_id: str,
        fee_amount: float,
        fee_currency: str = "EUR"
    ) -> LedgerEntry:
        """Record fee collection."""
        return await self.record_ledger_entry(
            entry_type=LedgerEntryType.FEE_ALLOCATION,
            amount=fee_amount,
            currency=fee_currency,
            amount_eur_equivalent=fee_amount if fee_currency == "EUR" else None,
            quote_id=quote_id,
            description=f"Fee collected: {fee_amount} {fee_currency}"
        )
    
    async def get_balance(self, currency: str = "EUR") -> float:
        """Get current balance for a currency."""
        # Get last ledger entry for this currency
        last_entry = await self.ledger_collection.find_one(
            {"currency": currency},
            sort=[("sequence_number", -1)]
        )
        
        if last_entry:
            return last_entry.get("balance_after", 0.0)
        return 0.0
    
    async def get_all_balances(self) -> Dict[str, float]:
        """Get balances for all currencies."""
        balances = {}
        
        for currency in self._config.supported_currencies:
            balances[currency] = await self.get_balance(currency)
        
        return balances
    
    async def get_total_eur_equivalent(self, rate_snapshot: Optional[Dict] = None) -> float:
        """Get total treasury value in EUR equivalent."""
        balances = await self.get_all_balances()
        total = 0.0
        
        for currency, balance in balances.items():
            if currency == "EUR":
                total += balance
            else:
                rate = (rate_snapshot or {}).get(f"{currency}_EUR", self._get_default_rate(currency))
                total += balance * rate
        
        return total
    
    def _get_default_rate(self, currency: str) -> float:
        """Get default exchange rate for currency."""
        default_rates = {
            "NENO": 10000.0,  # €10,000 per NENO
            "BNB": 300.0,     # Approximate
            "USDT": 0.92,     # Approximate
            "USDC": 0.92,     # Approximate
        }
        return default_rates.get(currency, 1.0)
    
    async def calculate_coverage_ratio(self, total_exposure_eur: float) -> float:
        """Calculate treasury coverage ratio."""
        if total_exposure_eur <= 0:
            return float('inf')  # No exposure = infinite coverage
        
        total_treasury = await self.get_total_eur_equivalent()
        return total_treasury / total_exposure_eur
    
    async def create_snapshot(self, total_exposure_eur: float = 0.0) -> TreasurySnapshot:
        """Create point-in-time treasury snapshot."""
        now = datetime.now(timezone.utc)
        
        balances = await self.get_all_balances()
        total_eur = await self.get_total_eur_equivalent()
        
        # Calculate real vs virtual
        virtual_floor = self._config.virtual_floor_eur if self._config.virtual_floor_enabled else 0.0
        real_balance = total_eur - virtual_floor
        if real_balance < 0:
            real_balance = 0.0
        
        coverage_ratio = await self.calculate_coverage_ratio(total_exposure_eur)
        
        snapshot = TreasurySnapshot(
            snapshot_id=f"snap_{uuid4().hex[:12]}",
            timestamp=now.isoformat(),
            balances=balances,
            total_eur_equivalent=total_eur,
            virtual_floor_eur=virtual_floor,
            real_balance_eur=real_balance,
            total_exposure_eur=total_exposure_eur,
            coverage_ratio=coverage_ratio if coverage_ratio != float('inf') else 999.99,
            last_sequence_number=self._sequence_counter,
            last_entry_id=self._last_entry_hash or "none"
        )
        
        # Generate checksum
        snapshot.checksum = hashlib.sha256(
            f"{snapshot.snapshot_id}|{snapshot.timestamp}|{snapshot.total_eur_equivalent}|{snapshot.last_sequence_number}".encode()
        ).hexdigest()[:16]
        
        # Store snapshot
        await self.snapshots_collection.insert_one(snapshot.to_dict())
        
        logger.info(
            f"Treasury Snapshot: {snapshot.snapshot_id} | "
            f"€{total_eur:,.2f} total | "
            f"Coverage: {coverage_ratio:.2%}"
        )
        
        return snapshot
    
    async def get_latest_snapshot(self) -> Optional[TreasurySnapshot]:
        """Get most recent treasury snapshot."""
        doc = await self.snapshots_collection.find_one(
            {}, sort=[("timestamp", -1)]
        )
        if doc:
            return TreasurySnapshot(**{k: v for k, v in doc.items() if k != "_id"})
        return None
    
    async def get_ledger_entries(
        self,
        quote_id: Optional[str] = None,
        entry_type: Optional[LedgerEntryType] = None,
        start_sequence: Optional[int] = None,
        end_sequence: Optional[int] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Query ledger entries."""
        query = {}
        
        if quote_id:
            query["quote_id"] = quote_id
        if entry_type:
            query["entry_type"] = entry_type.value
        if start_sequence is not None:
            query["sequence_number"] = {"$gte": start_sequence}
        if end_sequence is not None:
            query.setdefault("sequence_number", {})["$lte"] = end_sequence
        
        cursor = self.ledger_collection.find(
            query, {"_id": 0}
        ).sort("sequence_number", -1).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def verify_ledger_integrity(self, start_sequence: int = 1, end_sequence: Optional[int] = None) -> Tuple[bool, List[Dict]]:
        """
        Verify ledger chain integrity.
        
        Returns (is_valid, discrepancies)
        """
        discrepancies = []
        
        if end_sequence is None:
            end_sequence = self._sequence_counter
        
        cursor = self.ledger_collection.find(
            {"sequence_number": {"$gte": start_sequence, "$lte": end_sequence}},
            {"_id": 0}
        ).sort("sequence_number", 1)
        
        entries = await cursor.to_list(length=end_sequence - start_sequence + 1)
        
        prev_hash = None
        prev_balance = {}
        
        for entry in entries:
            # Check sequence continuity
            expected_seq = (entries[0]["sequence_number"] if entry == entries[0] 
                          else entries[entries.index(entry) - 1]["sequence_number"] + 1)
            if entry["sequence_number"] != expected_seq:
                discrepancies.append({
                    "type": "sequence_gap",
                    "expected": expected_seq,
                    "actual": entry["sequence_number"],
                    "entry_id": entry["entry_id"]
                })
            
            # Check hash chain
            if prev_hash and entry.get("previous_entry_hash") != prev_hash:
                discrepancies.append({
                    "type": "hash_chain_break",
                    "entry_id": entry["entry_id"],
                    "expected_prev_hash": prev_hash,
                    "actual_prev_hash": entry.get("previous_entry_hash")
                })
            
            # Check balance continuity
            currency = entry["currency"]
            if currency in prev_balance:
                expected_balance = prev_balance[currency] + entry["amount"]
                if abs(entry["balance_after"] - expected_balance) > 0.01:
                    discrepancies.append({
                        "type": "balance_mismatch",
                        "entry_id": entry["entry_id"],
                        "expected": expected_balance,
                        "actual": entry["balance_after"]
                    })
            
            prev_hash = entry.get("audit_hash")
            prev_balance[currency] = entry["balance_after"]
        
        is_valid = len(discrepancies) == 0
        return is_valid, discrepancies
    
    async def get_treasury_summary(self) -> Dict:
        """Get comprehensive treasury summary."""
        balances = await self.get_all_balances()
        total_eur = await self.get_total_eur_equivalent()
        
        # Get recent entries
        recent_entries = await self.get_ledger_entries(limit=10)
        
        return {
            "balances": balances,
            "total_eur_equivalent": total_eur,
            "virtual_floor_eur": self._config.virtual_floor_eur,
            "real_balance_eur": max(0, total_eur - self._config.virtual_floor_eur),
            "last_sequence": self._sequence_counter,
            "config": self._config.to_dict(),
            "recent_entries": recent_entries[:5]
        }


# Global instance
_treasury_service: Optional[TreasuryService] = None


def get_treasury_service() -> Optional[TreasuryService]:
    return _treasury_service


def set_treasury_service(service: TreasuryService):
    global _treasury_service
    _treasury_service = service

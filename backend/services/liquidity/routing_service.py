"""
Market Routing Service.

Provides venue-agnostic market routing for post-settlement conversions:
- Abstract connector interface for CEX/DEX venues
- Best-execution routing logic
- Fallback path selection
- Shadow mode execution (log-only)

Phase 1: Shadow mode only - all routing is simulated and logged.
Phase 2: Real venue integration (Binance, Kraken, etc.)
"""

from services.institutional.dark_pool import DarkPool
from services.institutional.rfq_engine import RFQEngine
from services.profit.advanced_sor import AdvancedSOR


from __future__ import annotations

from services.exchanges.connector_manager import get_connector_manager


class MarketRoutingService:
    def __init__(self, db):
        self.db = db
        self._initialized = False
        self._shadow_mode = True

    async def initialize(self):
        self._shadow_mode = False
        self._initialized = True

    def _is_internal_asset(self, symbol: str):
        up = symbol.upper()
        return "NENO" in up or up.startswith("TKN") or "-TKN" in up or "TKN-" in up

    async def execute_conversion(
        self,
        source_currency,
        source_amount,
        destination_currency,
        exposure_id=None,
        quote_id=None,
    ):
        manager = get_connector_manager()
        symbol = f"{source_currency}-{destination_currency}"

        order, error = await manager.execute_order(
            symbol=symbol,
            side="sell",
            quantity=source_amount,
            user_id="routing_engine",
        )
        if error:
            raise Exception(error)

        return type("ConversionResult", (), {
            "conversion_id": f"conv_{getattr(order, 'order_id', 'unknown')}",
            "destination_amount": getattr(order, "filled_quantity", 0.0) * getattr(order, "average_price", 0.0),
        })


import logging
from typing import Optional, Dict, List, Tuple, Protocol
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from abc import ABC, abstractmethod
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.liquidity.routing_models import (
    RoutingVenue,
    RoutingStatus,
    ConversionPath,
    MarketConversionEvent,
    RoutingConfig
)

from services.exchanges.connector_manager import get_connector_manager

class MarketRoutingService:

    def __init__(self, db):
        self.dark_pool = DarkPool()
        self.rfq = RFQEngine()
        self.sor = AdvancedSOR()
        self.db = db
        self._initialized = False
        self._shadow_mode = True

    async def initialize(self):
        self._shadow_mode = False
        self._initialized = True

    def _is_internal_asset(self, symbol: str):
        up = symbol.upper()
        return "NENO" in up or up.startswith("TKN")

    async def execute_conversion(
        self,
        source_currency,
        source_amount,
        destination_currency,
        exposure_id=None,
        quote_id=None
    ):
        manager = get_connector_manager()

        symbol = f"{source_currency}{destination_currency}"

        if self._is_internal_asset(symbol):
            order, error = await manager.execute_order(
                symbol=symbol,
                side="sell",
                quantity=source_amount
            )
        else:
            order, error = await manager.execute_order(
                symbol=symbol,
                side="sell",
                quantity=source_amount
            )

        if error:
            raise Exception(error)

        return {
            "conversion_id": "real_" + str(order.order_id),
            "destination_amount": order.filled_quantity * order.average_price
        }


logger = logging.getLogger(__name__)


class VenueConnector(ABC):
    """Abstract base class for venue connectors."""
    
    @property
    @abstractmethod
    def venue(self) -> RoutingVenue:
        """Return the venue identifier."""
        pass
    
    @abstractmethod
    async def get_quote(
        self,
        source_currency: str,
        destination_currency: str,
        amount: float
    ) -> Optional[Dict]:
        """Get a quote for conversion."""
        pass
    
    @abstractmethod
    async def execute_conversion(
        self,
        source_currency: str,
        destination_currency: str,
        amount: float,
        quote_id: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Execute a conversion. Returns (success, result, error)."""
        pass
    
    @abstractmethod
    async def get_balance(self, currency: str) -> float:
        """Get available balance for a currency."""
        pass


class ShadowVenueConnector(VenueConnector):
    """
    Shadow mode venue connector.
    
    Simulates market routing without real execution.
    All operations are logged for observability.
    """
    
    def __init__(self, simulated_rates: Optional[Dict] = None):
        self._simulated_rates = simulated_rates or {
            "NENO_BNB": 33.33,      # 10000 EUR / 300 EUR per BNB
            "NENO_USDT": 10869.57,  # 10000 EUR / 0.92 EUR per USDT
            "BNB_USDT": 326.09,     # 300 EUR / 0.92 EUR
            "BNB_EUR": 300.0,
            "USDT_EUR": 0.92,
            "USDC_EUR": 0.92,
            "NENO_EUR": 10000.0
        }
        self._simulated_balances = {
            "NENO": 1000.0,
            "BNB": 100.0,
            "USDT": 500000.0,
            "USDC": 500000.0,
            "EUR": 10000000.0
        }
    
    @property
    def venue(self) -> RoutingVenue:
        return RoutingVenue.SHADOW
    
    async def get_quote(
        self,
        source_currency: str,
        destination_currency: str,
        amount: float
    ) -> Optional[Dict]:
        """Get simulated quote."""
        rate_key = f"{source_currency}_{destination_currency}"
        rate = self._simulated_rates.get(rate_key)
        
        if rate is None:
            # Try reverse
            reverse_key = f"{destination_currency}_{source_currency}"
            reverse_rate = self._simulated_rates.get(reverse_key)
            if reverse_rate:
                rate = 1.0 / reverse_rate
        
        if rate is None:
            return None
        
        # Simulate slippage (0.1-0.5%)
        import random
        slippage = random.uniform(0.001, 0.005)
        effective_rate = rate * (1 - slippage)
        
        return {
            "venue": self.venue.value,
            "source_currency": source_currency,
            "destination_currency": destination_currency,
            "source_amount": amount,
            "destination_amount": amount * effective_rate,
            "rate": effective_rate,
            "slippage_pct": slippage * 100,
            "fee_pct": 0.1,  # 0.1% fee
            "valid_for_seconds": 30,
            "quote_id": f"shadow_quote_{uuid4().hex[:8]}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def execute_conversion(
        self,
        source_currency: str,
        destination_currency: str,
        amount: float,
        quote_id: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Execute simulated conversion."""
        quote = await self.get_quote(source_currency, destination_currency, amount)
        
        if not quote:
            return False, None, f"No route available for {source_currency} -> {destination_currency}"
        
        result = {
            "venue": self.venue.value,
            "order_id": f"shadow_order_{uuid4().hex[:12]}",
            "trade_ids": [f"shadow_trade_{uuid4().hex[:8]}"],
            "source_currency": source_currency,
            "source_amount": amount,
            "destination_currency": destination_currency,
            "destination_amount": quote["destination_amount"],
            "executed_rate": quote["rate"],
            "slippage_pct": quote["slippage_pct"],
            "fee_amount": amount * quote["fee_pct"] / 100,
            "fee_currency": source_currency,
            "status": "completed",
            "is_shadow": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(
            f"[SHADOW] Conversion executed: {amount} {source_currency} -> "
            f"{quote['destination_amount']:.4f} {destination_currency} @ {quote['rate']:.6f}"
        )
        
        return True, result, None
    
    async def get_balance(self, currency: str) -> float:
        """Get simulated balance."""
        return self._simulated_balances.get(currency, 0.0)


class MarketRoutingService:
    """
    Market routing service for post-settlement conversions.
    
    Features:
    - Venue-agnostic connector interface
    - Best-execution path selection
    - Fallback routing
    - Shadow mode (log-only execution)
    - Full audit trail
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.conversions_collection = db.market_conversion_events
        self.config_collection = db.routing_config
        
        self._initialized = False
        self._config: Optional[RoutingConfig] = None
        self._connectors: Dict[RoutingVenue, VenueConnector] = {}
    
    async def initialize(self):
        """Initialize routing service."""
        if self._initialized:
            return
        
        # Create indexes
        await self.conversions_collection.create_index("conversion_id", unique=True)
        await self.conversions_collection.create_index("quote_id")
        await self.conversions_collection.create_index("exposure_id")
        await self.conversions_collection.create_index("status")
        await self.conversions_collection.create_index("created_at")
        
        # Load or create config
        self._config = await self._load_or_create_config()
        
        # Initialize shadow connector (always available)
        self._connectors[RoutingVenue.SHADOW] = ShadowVenueConnector()
        from services.liquidity.real_venue_connector import RealVenueConnector

self._connectors[RoutingVenue.CEX] = RealVenueConnector()

        
        self._initialized = True
        logger.info(
            f"Market Routing Service initialized:\n"
            f"  Shadow Mode: {self._config.shadow_mode}\n"
            f"  Primary Venue: {self._config.primary_venue.value}\n"
            f"  Conversion Path: {' -> '.join(self._config.neno_conversion_path)}"
        )
    
    async def _load_or_create_config(self) -> RoutingConfig:
        """Load or create routing configuration."""
        config_doc = await self.config_collection.find_one({"config_type": "routing"})
        
        if config_doc:
            return RoutingConfig(
                shadow_mode=False
                enabled_venues=[RoutingVenue.CEX]
                primary_venue=RoutingVenue.CEX
                neno_conversion_path=config_doc.get("neno_conversion_path", ["NENO", "BNB", "USDT", "EUR"]),
                max_slippage_pct=config_doc.get("max_slippage_pct", 1.0),
                max_retries=config_doc.get("max_retries", 3),
                execution_timeout_seconds=config_doc.get("execution_timeout_seconds", 300),
                use_best_execution=config_doc.get("use_best_execution", True),
                split_large_orders=config_doc.get("split_large_orders", True),
                large_order_threshold_eur=config_doc.get("large_order_threshold_eur", 50000.0)
            )
        
        # Create default config (shadow mode)
        config = RoutingConfig()
        await self.config_collection.insert_one({
            "config_type": "routing",
            **config.to_dict(),
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        return config
    
    def register_connector(self, connector: VenueConnector):
        """Register a venue connector."""
        self._connectors[connector.venue] = connector
        logger.info(f"Registered connector for venue: {connector.venue.value}")
    
    async def get_conversion_path(
        self,
        source_currency: str,
        destination_currency: str,
        amount: float
    ) -> Optional[ConversionPath]:
        """
        Get optimal conversion path.
        
        For NENO -> EUR, uses configured path (e.g., NENO -> BNB -> USDT -> EUR)
        """
        now = datetime.now(timezone.utc)
        
        # Determine path steps
        if source_currency == "NENO" and destination_currency == "EUR":
            path_currencies = self._config.neno_conversion_path
        else:
            path_currencies = [source_currency, destination_currency]
        
        # Build steps
        steps = []
        for i in range(len(path_currencies) - 1):
            from_curr = path_currencies[i]
            to_curr = path_currencies[i + 1]
            
            # Get quote from primary connector
            connector = self._connectors.get(self._config.primary_venue)
            if not connector:
                connector = self._connectors.get(RoutingVenue.SHADOW)
            
            quote = await connector.get_quote(from_curr, to_curr, amount)
            
            steps.append({
                "from": from_curr,
                "to": to_curr,
                "venue": connector.venue.value,
                "estimated_rate": quote["rate"] if quote else 0,
                "estimated_output": quote["destination_amount"] if quote else 0
            })
            
            # Update amount for next step
            if quote:
                amount = quote["destination_amount"]
        
        # Calculate overall metrics
        if steps and steps[-1].get("estimated_output", 0) > 0:
            overall_rate = steps[-1]["estimated_output"] / amount if amount > 0 else 0
            
            path = ConversionPath(
                path_id=f"path_{uuid4().hex[:12]}",
                source_currency=source_currency,
                destination_currency=destination_currency,
                steps=steps,
                estimated_rate=overall_rate,
                estimated_slippage_pct=0.3,  # Aggregate estimate
                estimated_fee_pct=0.1 * len(steps),
                estimated_total_cost_pct=0.3 + 0.1 * len(steps),
                liquidity_score=85.0,
                reliability_score=95.0,
                execution_time_estimate_seconds=60 * len(steps),
                created_at=now.isoformat(),
                valid_until=(now + timedelta(seconds=60)).isoformat()
            )
            
            return path
        
        return None
    
    async def execute_conversion(
        self,
        source_currency: str,
        source_amount: float,
        destination_currency: str,
        exposure_id: Optional[str] = None,
        quote_id: Optional[str] = None,
        hedge_id: Optional[str] = None
    ) -> MarketConversionEvent:
        """
        Execute market conversion.
        
        In shadow mode, this simulates the conversion and logs all details.
        """
        now = datetime.now(timezone.utc)
        
        # Get conversion path
        path = await self.get_conversion_path(source_currency, destination_currency, source_amount)
        
        # Create conversion event
        event = MarketConversionEvent(
            conversion_id=f"conv_{uuid4().hex[:12]}",
            status=RoutingStatus.PROPOSED if self._config.shadow_mode else RoutingStatus.QUEUED,
            source_currency=source_currency,
            source_amount=source_amount,
            destination_currency=destination_currency,
            venue=RoutingVenue.CEX
            path=path,
            exposure_id=exposure_id,
            quote_id=quote_id,
            hedge_id=hedge_id,
            is_shadow=False
            created_at=now.isoformat()
        )
        
        # Get rate snapshot before
        event.rate_snapshot_before = await self._get_rate_snapshot()
        
        # Execute (shadow or real)
        symbol = f"{source_currency}-{destination_currency}"

# 🔥 1. DARK POOL (ORDINI GRANDI)
if source_amount > 50000:
    await self.dark_pool.submit_order("sell", source_amount)
    match = await self.dark_pool.match()
    if match["status"] == "matched":
        event.status = RoutingStatus.COMPLETED
        event.destination_amount = source_amount
        return event

# 🔥 2. RFQ (ISTITUZIONALE)
if source_amount > 10000:
    quote = await self.rfq.request_quote(symbol, source_amount)
    execution = await self.rfq.execute(quote)

    event.status = RoutingStatus.COMPLETED
    event.destination_amount = source_amount * execution["price"]
    return event

# 🔥 3. SMART ORDER ROUTING
venues = [
    {"venue": "binance", "price": 100},
    {"venue": "coinbase", "price": 101}
]

best = await self.sor.route(venues)

connector = self._connectors.get(self._config.primary_venue)

        # 🔥 REAL EXECUTION

success, result, error = await connector.execute_conversion(
    source_currency,
    destination_currency,
    source_amount
)

if success and result:
    event.status = RoutingStatus.COMPLETED
    event.destination_amount = result["destination_amount"]
    event.executed_rate = result["executed_rate"]
    event.venue_order_id = result["order_id"]
    event.completed_at = now.isoformat()
else:
    event.status = RoutingStatus.FAILED
    event.error_message = error

        
        # Get rate snapshot after
        event.rate_snapshot_after = await self._get_rate_snapshot()
        
        # Store event
        await self.conversions_collection.insert_one(event.to_dict())
        
        logger.info(
            f"[{'SHADOW' if event.is_shadow else 'LIVE'}] Market Conversion: "
            f"{source_amount} {source_currency} -> "
            f"{event.destination_amount:.4f} {destination_currency} | "
            f"Status: {event.status.value}"
        )
        
        return event
    
    async def _get_rate_snapshot(self) -> Dict:
        """Get current rate snapshot."""
        # In production, this would fetch real market rates
        # For now, return simulated rates
        return {
            "NENO_EUR": 10000.0,
            "BNB_EUR": 300.0,
            "USDT_EUR": 0.92,
            "USDC_EUR": 0.92,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def get_conversion(self, conversion_id: str) -> Optional[Dict]:
        """Get conversion by ID."""
        doc = await self.conversions_collection.find_one(
            {"conversion_id": conversion_id},
            {"_id": 0}
        )
        return doc
    
    async def get_conversions_by_quote(self, quote_id: str) -> List[Dict]:
        """Get all conversions for a quote."""
        cursor = self.conversions_collection.find(
            {"quote_id": quote_id},
            {"_id": 0}
        ).sort("created_at", -1)
        
        return await cursor.to_list(length=100)
    
    async def get_pending_conversions(self) -> List[Dict]:
        """Get all pending conversions."""
        cursor = self.conversions_collection.find(
            {"status": {"$in": [
                RoutingStatus.QUEUED.value,
                RoutingStatus.EXECUTING.value,
                RoutingStatus.PARTIAL.value
            ]}},
            {"_id": 0}
        ).sort("created_at", 1)
        
        return await cursor.to_list(length=100)
    
    async def get_routing_summary(self) -> Dict:
        """Get routing service summary."""
        # Aggregate conversions by status
        pipeline = [
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "total_source": {"$sum": "$source_amount"},
                    "total_destination": {"$sum": "$destination_amount"}
                }
            }
        ]
        
        results = await self.conversions_collection.aggregate(pipeline).to_list(length=20)
        
        return {
            "config": self._config.to_dict(),
            "by_status": {r["_id"]: {
                "count": r["count"],
                "total_source": r["total_source"],
                "total_destination": r["total_destination"]
            } for r in results},
            "enabled_connectors": list(self._connectors.keys()),
            "shadow_mode": self._config.shadow_mode
        }
    
    async def simulate_conversion(
        self,
        quote_id: str,
        source_currency: str,
        destination_currency: str,
        source_amount: float,
        exposure_id: Optional[str] = None
    ) -> Optional[MarketConversionEvent]:
        """
        Simulate a market conversion (shadow-mode only).
        
        This method always runs in shadow mode regardless of config,
        and is used to log what conversion would happen for audit purposes.
        """
        # Force shadow mode for this operation
        original_shadow = self._config.shadow_mode
        self._config.shadow_mode = True
        
        try:
            event = await self.execute_conversion(
                source_currency=source_currency,
                source_amount=source_amount,
                destination_currency=destination_currency,
                exposure_id=exposure_id,
                quote_id=quote_id
            )
            
            # Mark as simulation
            if event:
                await self.conversions_collection.update_one(
                    {"conversion_id": event.conversion_id},
                    {"$set": {"is_simulation": True, "simulation_reason": "lifecycle_hook"}}
                )
            
            return event
        finally:
            # Restore original shadow mode setting
            self._config.shadow_mode = original_shadow


# Global instance
_routing_service: Optional[MarketRoutingService] = None


def get_routing_service() -> Optional[MarketRoutingService]:
    return _routing_service


def set_routing_service(service: MarketRoutingService):
    global _routing_service
    _routing_service = service

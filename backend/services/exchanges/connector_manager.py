"""
Connector Manager - Manages multiple exchange connectors.

Provides:
- Unified interface for multiple exchanges
- Automatic failover between venues
- Order routing and execution
- Balance aggregation
- NENO virtual exchange integration
"""


import os
import logging
from services.exchanges.neno_virtual_exchange import neno_exchange

from typing import Optional, Dict, List, Tuple
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from .base_connector import (
    ExchangeConnector,
    OrderSide,
    OrderType,
    OrderStatus,
    ExchangeOrder,
    ExchangeBalance,
    MarketTicker
)
from  services.exchange.binance_connector import BinanceConnector
from .kraken_connector import KrakenConnector
from .coinbase_connector import CoinbaseConnector
from .mexc_connector import MexcConnector
from .neno_virtual_exchange import get_neno_exchange, NenoVirtualExchange

from __future__ import annotations

from services.exchanges.neno_virtual_exchange import neno_exchange
from services.exchanges.binance_connector import BinanceConnector
from services.risk.trade_risk_engine import TradeRiskEngine


class ConnectorManager:
    def __init__(self):
        self._enabled = False
        self._shadow_mode = True
        self.binance = BinanceConnector()
        self.risk_engine = TradeRiskEngine()

    async def enable_live_trading(self, user_id="system"):
        self._enabled = True
        self._shadow_mode = False

    def _is_internal_symbol(self, symbol: str) -> bool:
        up = symbol.upper()
        return "NENO" in up or up.startswith("TKN") or "-TKN" in up or "TKN-" in up

    from services.risk.risk_engine import RiskEngine
from services.profit.ai_pricing_engine import AIPricingEngine
from services.clearing.clearing_engine import ClearingEngine
from services.treasury.netting_engine import NettingEngine

risk_engine = RiskEngine()
ai_pricing = AIPricingEngine()
clearing_engine = ClearingEngine()
netting_engine = NettingEngine()

async def execute_order(self, symbol, side, quantity, user_id="system"):

    # 🔴 1. RISK CHECK
    exposure = quantity  # semplificato (puoi migliorare)
    if not risk_engine.check(exposure):
        return None, "RISK_REJECTED"

    # 🔴 2. AI PRICING
    base_price_data = await self.get_best_price(symbol)
    if not base_price_data:
        return None, "NO_LIQUIDITY"

    ticker, venue = base_price_data
    price = ai_pricing.compute_price(ticker.last, quantity)

    # 🔴 3. INTERNAL (NENO / TOKEN CUSTOM)
    if self._is_internal_symbol(symbol):
        order = await neno_exchange.place_market_order(
            user_id,
            symbol,
            side,
            quantity
        )

    else:
        # 🔴 4. SOR → CEX
        order, error = await self._execute_cex_order(
            symbol,
            side,
            quantity
        )

        if error:
            return None, error

    # 🔴 5. CLEARING
    clearing_engine.settle({
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price
    })

    # 🔴 6. NETTING
    netting_engine.net(symbol, quantity if side == "buy" else -quantity)

    return order, None

        if not self._enabled:
            return None, "Trading not enabled"

        if self._is_internal_symbol(symbol):
            ticker, _ = await self.get_best_price(symbol)
            ref_price = ticker.last if ticker else 0.0
            notional = quantity * ref_price
            allowed, reason = await self.risk_engine.validate_notional(notional)
            if not allowed:
                return None, reason

            order = await neno_exchange.place_market_order(
                user_id=user_id,
                symbol=symbol,
                side=side,
                quantity=quantity,
            )
            return order, None

        return await self._execute_cex_order(symbol, side, quantity)

    async def _execute_cex_order(self, symbol, side, quantity):
        return await self.binance.place_market_order(symbol, side, quantity)

    async def get_best_price(self, symbol):
        if self._is_internal_symbol(symbol):
            ticker = await neno_exchange.get_ticker(symbol)
            return ticker, "neno_exchange"
        return await self.binance.get_ticker(symbol)

    async def get_aggregated_balance(self, currency: str):
        if currency.upper() == "NENO":
            return await neno_exchange.get_balance(currency)
        return await self.binance.get_balance(currency)


manager = ConnectorManager()


def get_connector_manager():
    return manager


logger = logging.getLogger(__name__)


"""
    Manages multiple exchange connectors with automatic failover.
    
    Features:
    - Multi-venue order routing
    - Automatic failover on errors
    - Balance aggregation
    - Best price selection
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.orders_collection = db.exchange_orders
        self.config_collection = db.exchange_config
        
        self._initialized = False
        self._connectors: Dict[str, ExchangeConnector] = {}
        self._primary_venue = "binance"
        self._fallback_venue = "kraken"
        self._enabled = False
        self._shadow_mode = True  # Start in shadow mode

        self.binance = BinanceConnector()

        async def enable_live_trading(self, user_id="system"):
        self._enabled = True
        self._shadow_mode = False

    def _is_internal_symbol(self, symbol: str) -> bool:
        up = symbol.upper()
        return "NENO" in up or up.startswith("TKN")

    async def execute_order(self, symbol, side, quantity, user_id="system"):
        if self._is_internal_symbol(symbol):
            return await self._execute_internal(symbol, side, quantity, user_id)

        return await self._execute_cex(symbol, side, quantity)

    async def _execute_internal(self, symbol, side, quantity, user_id):
        order = await neno_exchange.place_market_order(
            user_id=user_id,
            symbol=symbol,
            side=side,
            quantity=quantity
        )
        return order, None

    async def _execute_cex(self, symbol, side, quantity):
        return await self.binance.place_market_order(symbol, side, quantity)

    async def get_best_price(self, symbol):
        if self._is_internal_symbol(symbol):
            ticker = await neno_exchange.get_ticker(symbol)
            return ticker, "neno_exchange"

        return await self.binance.get_ticker(symbol)

manager = ConnectorManager()

def get_connector_manager():
    return manager

        
        # NENO Virtual Exchange
        self._neno_exchange: NenoVirtualExchange = get_neno_exchange()
    
    async def initialize_connectors(self):
    from services.exchanges.binance_connector import BinanceConnector
    from services.exchanges.coinbase_connector import CoinbaseConnector

    binance_key = os.getenv("BINANCE_API_KEY")
    binance_secret = os.getenv("BINANCE_API_SECRET")

    coinbase_key = os.getenv("COINBASE_API_KEY")
    coinbase_secret = os.getenv("COINBASE_API_SECRET")

    if binance_key and binance_secret:
        self._connectors["BINANCE"] = BinanceConnector(
            api_key=binance_key,
            api_secret=binance_secret
        )

    if coinbase_key and coinbase_secret:
        self._connectors["COINBASE"] = CoinbaseConnector(
            api_key=coinbase_key,
            api_secret=coinbase_secret
        )

        
        # Create indexes
        await self.orders_collection.create_index("order_id", unique=True)
        await self.orders_collection.create_index("exchange_order_id")
        await self.orders_collection.create_index("exchange")
        await self.orders_collection.create_index("status")
        await self.orders_collection.create_index("created_at")
        
        # Load configuration
        config = await self.config_collection.find_one({"config_type": "exchanges"})
        
        if config:
            self._enabled = config.get("enabled", False)
            self._shadow_mode = config.get("shadow_mode", True)
            self._primary_venue = config.get("primary_venue", "binance")
            self._fallback_venue = config.get("fallback_venue", "kraken")
        else:
            # Create default config
            await self.config_collection.insert_one({
                "config_type": "exchanges",
                "enabled": False,
                "shadow_mode": True,
                "primary_venue": "binance",
                "fallback_venue": "kraken",
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        
        # Initialize connectors (without credentials yet)
        self._connectors["binance"] = BinanceConnector()
        self._connectors["kraken"] = KrakenConnector()
        self._connectors["coinbase"] = CoinbaseConnector()
        self._connectors["mexc"] = MexcConnector()
        
        # Load and initialize credentials from environment
        await self._load_credentials()
        
        self._initialized = True
        logger.info(
            f"Connector Manager initialized:\n"
            f"  Enabled: {self._enabled}\n"
            f"  Shadow Mode: {self._shadow_mode}\n"
            f"  Primary: {self._primary_venue}\n"
            f"  Fallback: {self._fallback_venue}"
        )
    
    async def _load_credentials(self):
        """Load exchange credentials from environment."""
        # Binance
        binance_key = os.environ.get("BINANCE_API_KEY")
        binance_secret = os.environ.get("BINANCE_API_SECRET")
        binance_testnet = os.environ.get("BINANCE_TESTNET", "false").lower() == "true"
        
        if binance_key and binance_secret:
            await self._connectors["binance"].initialize(
                api_key=binance_key,
                api_secret=binance_secret,
                testnet=binance_testnet
            )
            await self._connectors["binance"].connect()
            logger.info("[CONNECTORS] Binance connector configured")
        else:
            logger.warning("[CONNECTORS] Binance credentials not configured")
        
        # Kraken
        kraken_key = os.environ.get("KRAKEN_API_KEY")
        kraken_secret = os.environ.get("KRAKEN_API_SECRET")
        
        if kraken_key and kraken_secret:
            await self._connectors["kraken"].initialize(
                api_key=kraken_key,
                api_secret=kraken_secret
            )
            await self._connectors["kraken"].connect()
            logger.info("[CONNECTORS] Kraken connector configured")
        else:
            logger.warning("[CONNECTORS] Kraken credentials not configured")
        
        # Coinbase
        coinbase_key = os.environ.get("COINBASE_API_KEY")
        coinbase_secret = os.environ.get("COINBASE_API_SECRET")
        
        if coinbase_key and coinbase_secret:
            await self._connectors["coinbase"].initialize(
                api_key=coinbase_key,
                api_secret=coinbase_secret
            )
            await self._connectors["coinbase"].connect()
            logger.info("[CONNECTORS] Coinbase connector configured")
        else:
            logger.warning("[CONNECTORS] Coinbase credentials not configured")
        
        # MEXC
        mexc_key = os.environ.get("MEXC_API_KEY")
        mexc_secret = os.environ.get("MEXC_API_SECRET", "")
        
        if mexc_key:
            await self._connectors["mexc"].initialize(
                api_key=mexc_key,
                api_secret=mexc_secret
            )
            await self._connectors["mexc"].connect()
            logger.info("[CONNECTORS] MEXC connector configured")
        else:
            logger.warning("[CONNECTORS] MEXC credentials not configured")
    
    def is_enabled(self) -> bool:
        """Check if exchange trading is enabled."""
        return self._enabled and not self._shadow_mode
    
    def is_shadow_mode(self) -> bool:
        """Check if in shadow mode (simulated trades)."""
        return self._shadow_mode
    
    def get_connector(self, exchange: str) -> Optional[ExchangeConnector]:
        """Get a specific exchange connector."""
        return self._connectors.get(exchange)
    
    def _is_neno_symbol(self, symbol: str) -> bool:
        """Check if symbol is a NENO trading pair."""
        return 'NENO' in symbol.upper()
    
    async def get_ticker(self, symbol: str, venue: str = None) -> Optional[MarketTicker]:
        """
        Get ticker for a symbol from a specific venue or best available.
        
        For NENO pairs, returns data from the virtual NENO exchange.
        """
        # Handle NENO pairs via virtual exchange
        if self._is_neno_symbol(symbol):
            neno_ticker = self._neno_exchange.get_ticker(symbol)
            if neno_ticker:
                return MarketTicker(
                    symbol=neno_ticker.symbol,
                    bid=neno_ticker.bid,
                    ask=neno_ticker.ask,
                    last=neno_ticker.last,
                    volume_24h=neno_ticker.volume_24h,
                    high_24h=neno_ticker.high_24h,
                    low_24h=neno_ticker.low_24h,
                    timestamp=neno_ticker.timestamp
                )
            return None
        
        # For non-NENO pairs, use regular connectors
        if venue:
            connector = self._connectors.get(venue)
            if connector and connector.is_connected():
                return await connector.get_ticker(symbol)
            return None
        
        # Get from any connected venue
        for name, connector in self._connectors.items():
            if connector.is_connected():
                ticker = await connector.get_ticker(symbol)
                if ticker:
                    return ticker
        
        return None
    
    async def get_best_price(self, symbol: str) -> Tuple[Optional[MarketTicker], str]:
        """Get best price across all connected venues."""
        best_ticker = None
        best_venue = ""
        
        # Handle NENO pairs via virtual exchange
        if self._is_neno_symbol(symbol):
            neno_ticker = self._neno_exchange.get_ticker(symbol)
            if neno_ticker:
                return MarketTicker(
                    symbol=neno_ticker.symbol,
                    bid=neno_ticker.bid,
                    ask=neno_ticker.ask,
                    last=neno_ticker.last,
                    volume_24h=neno_ticker.volume_24h,
                    high_24h=neno_ticker.high_24h,
                    low_24h=neno_ticker.low_24h,
                    timestamp=neno_ticker.timestamp
                ), "neno_exchange"
        
        for name, connector in self._connectors.items():
            if not connector.is_connected():
                continue
            
            ticker = await connector.get_ticker(symbol)
            if ticker:
                if best_ticker is None or ticker.ask < best_ticker.ask:
                    best_ticker = ticker
                    best_venue = name
        
        return best_ticker, best_venue
    
    async def get_all_balances(self) -> Dict[str, List[ExchangeBalance]]:
        """Get balances from all connected venues including NENO."""
        all_balances = {}
        
        # Add NENO virtual exchange balance
        neno_balance = self._neno_exchange.get_balance('system')
        all_balances['neno_exchange'] = [
            ExchangeBalance(
                currency='NENO',
                total=neno_balance.total,
                available=neno_balance.available,
                locked=neno_balance.locked
            )
        ]
        
        for name, connector in self._connectors.items():
            if connector.is_connected():
                balances = await connector.get_balances()
                all_balances[name] = balances
        
        return all_balances
    
    async def get_aggregated_balance(self, currency: str) -> Dict[str, float]:
        """Get aggregated balance for a currency across all venues."""
        result = {
            "total": 0,
            "available": 0,
            "locked": 0,
            "by_venue": {}
        }
        
        # Add NENO balance if querying NENO
        if currency.upper() == 'NENO':
            neno_balance = self._neno_exchange.get_balance('system')
            result["total"] += neno_balance.total
            result["available"] += neno_balance.available
            result["locked"] += neno_balance.locked
            result["by_venue"]['neno_exchange'] = {
                'currency': 'NENO',
                'total': neno_balance.total,
                'available': neno_balance.available,
                'locked': neno_balance.locked
            }
        
        for name, connector in self._connectors.items():
            if connector.is_connected():
                balance = await connector.get_balance(currency)
                if balance:
                    result["total"] += balance.total
                    result["available"] += balance.available
                    result["locked"] += balance.locked
                    result["by_venue"][name] = balance.to_dict()
        
        return result
    
    async def execute_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        venue: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Tuple[ExchangeOrder, Optional[str]]:
        """
        Execute an order on the best venue or specified venue.
        
        For NENO pairs, routes to the virtual NENO exchange.
        
        Returns:
            Tuple of (ExchangeOrder, error_message)
        """
        now = datetime.now(timezone.utc)
        
        # Handle NENO orders via virtual exchange
        if self._is_neno_symbol(symbol):
            return await self._execute_neno_order(
                symbol, side, quantity, order_type, price, client_order_id
            )
        
        # Check if trading is enabled
        if not self._enabled:
            return self._create_shadow_order(
                symbol, side, quantity, order_type, price,
                "trading_disabled", "Exchange trading is disabled"
            ), "Exchange trading is disabled"
        
        if self._shadow_mode:
            return self._create_shadow_order(
                symbol, side, quantity, order_type, price,
                "shadow_mode", "Operating in shadow mode"
            ), None
        
        # Select venue
        target_venue = venue or self._primary_venue
        connector = self._connectors.get(target_venue)
        
        if not connector or not connector.is_connected():
            # Try fallback
            target_venue = self._fallback_venue
            connector = self._connectors.get(target_venue)
            
            if not connector or not connector.is_connected():
                return self._create_shadow_order(
                    symbol, side, quantity, order_type, price,
                    "no_venue", "No connected venues available"
                ), "No connected venues available"
        
        # Execute order
        try:
            if order_type == OrderType.MARKET:
                order = await connector.place_market_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    client_order_id=client_order_id
                )
            else:
                if price is None:
                    return self._create_shadow_order(
                        symbol, side, quantity, order_type, price,
                        "no_price", "Price required for limit orders"
                    ), "Price required for limit orders"
                
                order = await connector.place_limit_order(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    price=price,
                    client_order_id=client_order_id
                )
            
            # Store order
            await self.orders_collection.insert_one({
                **order.to_dict(),
                "is_shadow": False,
                "stored_at": now.isoformat()
            })
            
            return order, None
            
        except Exception as e:
            logger.error(f"[CONNECTORS] Order execution error: {e}")
            
            # Try fallback venue
            if target_venue == self._primary_venue:
                fallback_connector = self._connectors.get(self._fallback_venue)
                if fallback_connector and fallback_connector.is_connected():
                    logger.info(f"[CONNECTORS] Failing over to {self._fallback_venue}")
                    return await self.execute_order(
                        symbol, side, quantity, order_type, price,
                        self._fallback_venue, client_order_id
                    )
            
            return self._create_shadow_order(
                symbol, side, quantity, order_type, price,
                "execution_error", str(e)
            ), str(e)
    
    def _create_shadow_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        price: Optional[float],
        reason: str,
        message: str
    ) -> ExchangeOrder:
        """Create a shadow (simulated) order for logging."""
        from uuid import uuid4
        
        return ExchangeOrder(
            order_id=f"shadow_{uuid4().hex[:12]}",
            exchange="shadow",
            symbol=symbol,
            side=side,
            order_type=order_type,
            status=OrderStatus.PENDING,
            quantity=quantity,
            price=price,
            client_order_id=f"shadow_{reason}"
        )
    
    async def _execute_neno_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        price: Optional[float],
        client_order_id: Optional[str]
    ) -> Tuple[ExchangeOrder, Optional[str]]:
        """
        Execute an order for NENO via the virtual exchange.
        
        NENO orders are always executed (no shadow mode check)
        as they are managed by the platform directly.
        """
        try:
            side_str = side.value if isinstance(side, OrderSide) else side
            
            if order_type == OrderType.MARKET:
                neno_order = self._neno_exchange.place_market_order(
                    exchange='neno_exchange',
                    symbol=symbol,
                    side=side_str,
                    quantity=quantity,
                    user_id='system'
                )
            else:
                if price is None:
                    ticker = self._neno_exchange.get_ticker(symbol)
                    price = ticker.ask if side_str == 'buy' else ticker.bid
                
                neno_order = self._neno_exchange.place_limit_order(
                    exchange='neno_exchange',
                    symbol=symbol,
                    side=side_str,
                    quantity=quantity,
                    price=price,
                    user_id='system'
                )
            
            # Convert to ExchangeOrder
            status_map = {
                'filled': OrderStatus.FILLED,
                'open': OrderStatus.OPEN,
                'cancelled': OrderStatus.CANCELLED,
                'pending': OrderStatus.PENDING
            }
            
            order = ExchangeOrder(
                order_id=neno_order.order_id,
                exchange='neno_exchange',
                symbol=symbol,
                side=OrderSide(side_str),
                order_type=order_type,
                status=status_map.get(neno_order.status, OrderStatus.PENDING),
                quantity=quantity,
                price=neno_order.price,
                filled_quantity=neno_order.filled_quantity,
                average_price=neno_order.average_price,
                exchange_order_id=neno_order.order_id,
                client_order_id=client_order_id
            )
            
            # Save to database
            await self.orders_collection.insert_one({
                "order_id": order.order_id,
                "exchange": "neno_exchange",
                "symbol": symbol,
                "side": side_str,
                "order_type": order_type.value,
                "status": neno_order.status,
                "quantity": quantity,
                "price": neno_order.price,
                "filled_quantity": neno_order.filled_quantity,
                "average_price": neno_order.average_price,
                "fee": neno_order.fee,
                "created_at": neno_order.created_at,
                "filled_at": neno_order.filled_at,
                "is_neno": True
            })
            
            logger.info(
                f"[NENO] Order executed: {order.order_id} | "
                f"{side_str.upper()} {quantity:.4f} NENO @ €{neno_order.price:,.2f}"
            )
            
            return order, None
            
        except Exception as e:
            logger.error(f"[NENO] Order execution error: {e}")
            return self._create_shadow_order(
                symbol, side, quantity, order_type, price,
                "neno_error", str(e)
            ), str(e)
    
    async def enable_live_trading(self, user_id: str):
        """Enable live trading (disable shadow mode)."""
        self._shadow_mode = False
        self._enabled = True

        await self.initialize_connectors()

        print("🔥 LIVE TRADING ENABLED")
        
        await self.config_collection.update_one(
            {"config_type": "exchanges"},
            {
                "$set": {
                    "enabled": True,
                    "shadow_mode": False,
                    "enabled_at": datetime.now(timezone.utc).isoformat(),
                    "enabled_by": user_id
                }
            }
        )
        
        logger.info(f"[CONNECTORS] LIVE TRADING ENABLED by {user_id}")
    
    async def disable_live_trading(self, reason: str = None):
        """Disable live trading (enable shadow mode)."""
        self._shadow_mode = True
        
        await self.config_collection.update_one(
            {"config_type": "exchanges"},
            {
                "$set": {
                    "shadow_mode": True,
                    "disabled_at": datetime.now(timezone.utc).isoformat(),
                    "disabled_reason": reason
                }
            }
        )
        
        logger.warning(f"[CONNECTORS] LIVE TRADING DISABLED: {reason}")
    
    async def get_status(self) -> Dict:
        """Get connector manager status."""
        venues = {}
        
        for name, connector in self._connectors.items():
            venues[name] = {
                "initialized": connector.is_initialized(),
                "connected": connector.is_connected()
            }
        
        return {
            "enabled": self._enabled,
            "shadow_mode": self._shadow_mode,
            "primary_venue": self._primary_venue,
            "fallback_venue": self._fallback_venue,
            "venues": venues
        }


# Global instance
_connector_manager: Optional[ConnectorManager] = None


def get_connector_manager() -> Optional[ConnectorManager]:
    return _connector_manager


def set_connector_manager(manager: ConnectorManager):
    global _connector_manager
    _connector_manager = manager

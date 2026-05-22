"""
NENO Virtual Exchange Service - Provides $NENO as a virtual listing on exchanges.

Integrates $NENO token with exchange connectors as if it were a listed asset.
Uses fixed price of €10,000 per NENO with simulated order execution.

Features:
- Virtual ticker data for NENO/EUR, NENO/USD, NENO/USDT
- Simulated order execution with instant fill
- Balance tracking for NENO holdings
- Full audit logging
"""

import os
import logging
from services.profit.ai_pricing_engine
import AIPricingEngine
ai_pricing = AIPricingEngine()
from typing import Optional, Dict, List
from datetime import datetime, timezone
from dataclasses import dataclass, field
from uuid import uuid4
from decimal import Decimal

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from services.exchanges.neno_matching_engine import MatchingEngine
from services.pricing.market_maker import MarketMaker
from services.treasury.treasury_engine import TreasuryEngine


class NenoExchange:
    def __init__(self):
        self.engine = MatchingEngine()
        self.mm = MarketMaker()
        self.treasury = TreasuryEngine()
        self.user_balances: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.trade_history: Dict[str, List[Dict]] = defaultdict(list)

        # seed internal liquidity
        self._seed_book("NENO-EUR", 10000.0)
        self._seed_book("NENO-USDT", 10869.57)
        self._seed_book("NENO-BNB", 33.33)

    def _seed_book(self, symbol: str, reference_price: float):
        quote = self.mm.quote(
            reference_price=reference_price,
            inventory=100000.0,
            target_inventory=50000.0,
            volatility=0.02,
        )
        # maker liquidity internal
        self.engine.place_limit_order("mm_internal", symbol, "buy", 250.0, quote.bid)
        self.engine.place_limit_order("mm_internal", symbol, "sell", 250.0, quote.ask)

    def _split_symbol(self, symbol: str):
        if "-" in symbol:
            return symbol.split("-")
        if symbol == "NENOEUR":
            return "NENO", "EUR"
        if symbol == "NENOUSDT":
            return "NENO", "USDT"
        if symbol == "NENOBNB":
            return "NENO", "BNB"
        raise ValueError(f"Unsupported symbol: {symbol}")

    async def get_ticker(self, symbol: str):
        top = self.engine.get_top(symbol)
        bid = top["bid"] or 0.0
        ask = top["ask"] or 0.0
        last = (bid + ask) / 2.0 if bid and ask else 0.0

        return type("Ticker", (), {
            "bid": bid,
            "ask": ask,
            "last": last,
        })

    async def get_balance(self, currency: str):
        available = await self.treasury.get_available(currency)
        return {"currency": currency.upper(), "available": available}

    async def place_market_order(self, user_id, symbol, side, quantity):
        base_price = self._get_price(symbol)
        price = ai_pricing.compute_price(base_price,quantity)
        result = self.engine.place_market_order(user_id, symbol, side, quantity)

        filled = result["filled_quantity"]
        avg_price = result["average_price"]
        notional = filled * avg_price

        if filled > 0:
            if side == "buy":
                self.user_balances[user_id][base] += filled
                self.user_balances[user_id][quote] -= notional
                await self.treasury.adjust_balance(base, -filled)
                await self.treasury.adjust_balance(quote, notional)
            else:
                self.user_balances[user_id][base] -= filled
                self.user_balances[user_id][quote] += notional
                await self.treasury.adjust_balance(base, filled)
                await self.treasury.adjust_balance(quote, -notional)

        trade_record = {
            "order_id": result["order_id"],
            "user_id": user_id,
            "symbol": symbol,
            "side": side,
            "filled_quantity": filled,
            "average_price": avg_price,
            "status": result["status"],
            "trades": result["trades"],
        }
        self.trade_history[symbol].append(trade_record)

        return type("Order", (), {
            "order_id": result["order_id"],
            "average_price": avg_price,
            "filled_quantity": filled,
            "exchange_order_id": result["order_id"],
            "status": result["status"],
        })

    async def get_order_book(self, symbol: str):
        top = self.engine.get_top(symbol)
        return {
            "symbol": symbol,
            "best_bid": top["bid"],
            "best_ask": top["ask"],
        }

    async def get_trade_history(self, symbol: str):
        return self.trade_history[symbol][-100:]


neno_exchange = NenoExchange()

logger = logging.getLogger(__name__)

# NENO Configuration
NENO_PRICE_EUR = float(os.environ.get('NENO_PRICE_EUR', '10000.0'))
NENO_PRICE_USD = NENO_PRICE_EUR * 1.08  # Approximate EUR/USD rate
NENO_CONTRACT = os.environ.get('NENO_CONTRACT_ADDRESS', '0xeF3F5C1892A8d7A3304E4A15959E124402d69974')

# Supported NENO trading pairs
NENO_PAIRS = {
    'NENO-EUR': {'base': 'NENO', 'quote': 'EUR', 'price': NENO_PRICE_EUR},
    'NENO-USD': {'base': 'NENO', 'quote': 'USD', 'price': NENO_PRICE_USD},
    'NENO-USDT': {'base': 'NENO', 'quote': 'USDT', 'price': NENO_PRICE_USD},
    'NENOEUR': {'base': 'NENO', 'quote': 'EUR', 'price': NENO_PRICE_EUR},
    'NENOUSD': {'base': 'NENO', 'quote': 'USD', 'price': NENO_PRICE_USD},
    'NENOUSDT': {'base': 'NENO', 'quote': 'USDT', 'price': NENO_PRICE_USD},
}

class NenoExchange:

    def __init__(self):
        self.order_book = {
            "NENOUSDT": {
                "bid": 10000,
                "ask": 10050
            }
        }

    async def get_ticker(self, symbol):
        book = self.order_book.get(symbol, {})
        return type("Ticker", (), {
            "last": (book["bid"] + book["ask"]) / 2
        })

    async def place_market_order(self, user_id, symbol, side, quantity):
        ticker = await self.get_ticker(symbol)

        return type("Order", (), {
            "order_id": "neno_" + str(quantity),
            "average_price": ticker.last,
            "filled_quantity": quantity
        })

neno_exchange = NenoExchange()



@dataclass
class NenoTicker:
    """NENO ticker data."""
    symbol: str
    bid: float
    ask: float
    last: float
    volume_24h: float = 1250.5  # Simulated volume
    high_24h: float = 0
    low_24h: float = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def __post_init__(self):
        # Set high/low based on price with small variance
        if self.high_24h == 0:
            self.high_24h = self.last * 1.002
        if self.low_24h == 0:
            self.low_24h = self.last * 0.998
    
    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2
    
    @property
    def spread_pct(self) -> float:
        return ((self.ask - self.bid) / self.mid) * 100 if self.mid > 0 else 0


@dataclass
class NenoOrder:
    """NENO order record."""
    order_id: str
    exchange: str
    symbol: str
    side: str  # 'buy' or 'sell'
    order_type: str  # 'market' or 'limit'
    status: str  # 'filled', 'pending', 'cancelled'
    quantity: float
    price: float
    filled_quantity: float = 0
    average_price: float = 0
    fee: float = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    filled_at: Optional[str] = None


@dataclass
class NenoBalance:
    """NENO balance record."""
    currency: str = 'NENO'
    total: float = 0
    available: float = 0
    locked: float = 0


class NenoVirtualExchange:
    """
    Virtual exchange for $NENO token.
    
    Provides exchange-like functionality for NENO:
    - Ticker data with fixed price
    - Order execution (simulated)
    - Balance management
    """
    
    def __init__(self):
        self._balances: Dict[str, Dict[str, float]] = {}  # user_id -> {currency: balance}
        self._orders: Dict[str, NenoOrder] = {}
        self._initialized = True
        
        logger.info(f"[NENO-EXCHANGE] Virtual exchange initialized. NENO Price: €{NENO_PRICE_EUR:,.2f}")
    
    def is_neno_symbol(self, symbol: str) -> bool:
        """Check if symbol is a NENO pair."""
        symbol_upper = symbol.upper().replace('-', '')
        return 'NENO' in symbol_upper
    
    def get_neno_price(self, quote_currency: str = 'EUR') -> float:
        """Get NENO price in specified currency."""
        quote = quote_currency.upper()
        if quote in ['EUR']:
            return NENO_PRICE_EUR
        elif quote in ['USD', 'USDT', 'USDC']:
            return NENO_PRICE_USD
        else:
            return NENO_PRICE_EUR
    
    def get_ticker(self, symbol: str) -> Optional[NenoTicker]:
        """Get NENO ticker for a trading pair."""
        symbol_norm = symbol.upper().replace('-', '')
        
        # Determine quote currency
        if 'EUR' in symbol_norm:
            price = NENO_PRICE_EUR
        elif 'USD' in symbol_norm or 'USDT' in symbol_norm:
            price = NENO_PRICE_USD
        else:
            price = NENO_PRICE_EUR
        
        # Small spread simulation (0.1%)
        spread = price * 0.001
        
        return NenoTicker(
            symbol=symbol,
            bid=price - spread / 2,
            ask=price + spread / 2,
            last=price,
            volume_24h=1250.5 + (hash(datetime.now().minute) % 500),  # Varies slightly
        )
    
    def place_market_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        quantity: float,
        user_id: str = 'system'
    ) -> NenoOrder:
        """
        Execute a market order for NENO.
        
        Orders are instantly filled at the current NENO price.
        """
        order_id = f"neno_{uuid4().hex[:12]}"
        
        # Get price based on symbol
        ticker = self.get_ticker(symbol)
        price = ticker.ask if side.lower() == 'buy' else ticker.bid
        
        # Calculate fee (0.1%)
        fee = quantity * price * 0.001
        
        order = NenoOrder(
            order_id=order_id,
            exchange=exchange,
            symbol=symbol,
            side=side.lower(),
            order_type='market',
            status='filled',
            quantity=quantity,
            price=price,
            filled_quantity=quantity,
            average_price=price,
            fee=fee,
            filled_at=datetime.now(timezone.utc).isoformat()
        )
        
        self._orders[order_id] = order
        
        # Update balances
        self._update_balance(user_id, side, quantity, price)
        
        logger.info(
            f"[NENO-EXCHANGE] Market order filled: {order_id} | "
            f"{side.upper()} {quantity:.4f} NENO @ €{price:,.2f} on {exchange}"
        )
        
        return order
    
    def place_limit_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        user_id: str = 'system'
    ) -> NenoOrder:
        """
        Place a limit order for NENO.
        
        For simulation, limit orders near market price are instantly filled.
        """
        order_id = f"neno_{uuid4().hex[:12]}"
        
        ticker = self.get_ticker(symbol)
        market_price = ticker.mid
        
        # Check if limit price is executable
        is_executable = False
        if side.lower() == 'buy' and price >= ticker.ask:
            is_executable = True
        elif side.lower() == 'sell' and price <= ticker.bid:
            is_executable = True
        
        # Calculate fee
        fee = quantity * price * 0.001
        
        status = 'filled' if is_executable else 'open'
        filled_qty = quantity if is_executable else 0
        
        order = NenoOrder(
            order_id=order_id,
            exchange=exchange,
            symbol=symbol,
            side=side.lower(),
            order_type='limit',
            status=status,
            quantity=quantity,
            price=price,
            filled_quantity=filled_qty,
            average_price=price if is_executable else 0,
            fee=fee if is_executable else 0,
            filled_at=datetime.now(timezone.utc).isoformat() if is_executable else None
        )
        
        self._orders[order_id] = order
        
        if is_executable:
            self._update_balance(user_id, side, quantity, price)
        
        logger.info(
            f"[NENO-EXCHANGE] Limit order {'filled' if is_executable else 'placed'}: {order_id} | "
            f"{side.upper()} {quantity:.4f} NENO @ €{price:,.2f}"
        )
        
        return order
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        if order_id in self._orders:
            order = self._orders[order_id]
            if order.status == 'open':
                order.status = 'cancelled'
                logger.info(f"[NENO-EXCHANGE] Order cancelled: {order_id}")
                return True
        return False
    
    def get_order(self, order_id: str) -> Optional[NenoOrder]:
        """Get order by ID."""
        return self._orders.get(order_id)
    
    def get_open_orders(self, user_id: str = None, symbol: str = None) -> List[NenoOrder]:
        """Get all open orders."""
        orders = []
        for order in self._orders.values():
            if order.status == 'open':
                if symbol and order.symbol != symbol:
                    continue
                orders.append(order)
        return orders
    
    def get_balance(self, user_id: str = 'system') -> NenoBalance:
        """Get NENO balance for a user."""
        if user_id not in self._balances:
            self._balances[user_id] = {'NENO': 0, 'EUR': 100000}  # Default EUR balance
        
        neno_balance = self._balances[user_id].get('NENO', 0)
        return NenoBalance(
            currency='NENO',
            total=neno_balance,
            available=neno_balance,
            locked=0
        )
    
    def _update_balance(self, user_id: str, side: str, quantity: float, price: float):
        """Update user balances after trade."""
        if user_id not in self._balances:
            self._balances[user_id] = {'NENO': 0, 'EUR': 100000}
        
        if side.lower() == 'buy':
            self._balances[user_id]['NENO'] = self._balances[user_id].get('NENO', 0) + quantity
            self._balances[user_id]['EUR'] = self._balances[user_id].get('EUR', 100000) - (quantity * price)
        else:
            self._balances[user_id]['NENO'] = self._balances[user_id].get('NENO', 0) - quantity
            self._balances[user_id]['EUR'] = self._balances[user_id].get('EUR', 0) + (quantity * price)
    
    def get_trade_history(self, symbol: str = None, limit: int = 50) -> List[NenoOrder]:
        """Get trade history."""
        orders = [o for o in self._orders.values() if o.status == 'filled']
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return sorted(orders, key=lambda x: x.created_at, reverse=True)[:limit]


# Global instance
neno_exchange = NenoVirtualExchange()


def get_neno_exchange() -> NenoVirtualExchange:
    """Get the global NENO virtual exchange instance."""
    return neno_exchange

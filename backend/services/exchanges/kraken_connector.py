"""
Kraken Connector - Live trading integration with Kraken.

Supports:
- Spot trading (market and limit orders)
- Account balances
- Market data (tickers)

Symbol format: XXBTZEUR, XETHZEUR, etc. (Kraken uses X prefix for crypto)
"""

import os
import logging
import hmac
import hashlib
import base64
import time
import urllib.parse
import aiohttp
from typing import Optional, Dict, List
from datetime import datetime, timezone
from uuid import uuid4

from .base_connector import (
    ExchangeConnector,
    OrderSide,
    OrderType,
    OrderStatus,
    ExchangeOrder,
    ExchangeBalance,
    MarketTicker
)

logger = logging.getLogger(__name__)

# Kraken API endpoints
KRAKEN_API_URL = "https://api.kraken.com"


class KrakenConnector(ExchangeConnector):
    """
    Kraken exchange connector for live trading.
    
    Features:
    - Spot market and limit orders
    - Real-time balances
    - Market data access
    - HMAC-SHA512 authentication
    """
    
    def __init__(self):
        super().__init__("kraken")
        self._base_url = KRAKEN_API_URL
        self._session: Optional[aiohttp.ClientSession] = None
        self._api_version = "0"
    
    async def initialize(self, api_key: str, api_secret: str, **kwargs) -> bool:
        """Initialize with Kraken API credentials."""
        try:
            self._api_key = api_key
            self._api_secret = api_secret
            
            self._initialized = True
            logger.info("[KRAKEN] Initialized")
            return True
        except Exception as e:
            logger.error(f"[KRAKEN] Initialization failed: {e}")
            return False
    
    async def connect(self) -> bool:
        """Connect to Kraken API."""
        try:
            if self._session is None:
                self._session = aiohttp.ClientSession()
            
            # Test connection with server time
            async with self._session.get(f"{self._base_url}/0/public/Time") as response:
                data = await response.json()
                if len(data.get("error", [])) == 0:
                    self._connected = True
                    logger.info("[KRAKEN] Connected successfully")
                    return True
                else:
                    logger.error(f"[KRAKEN] Connection failed: {data['error']}")
                    return False
        except Exception as e:
            logger.error(f"[KRAKEN] Connection error: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from Kraken."""
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False
        logger.info("[KRAKEN] Disconnected")
    
    def _get_nonce(self) -> str:
        """Get nonce for authenticated requests."""
        return str(int(time.time() * 1000))
    
    def _generate_signature(self, url_path: str, data: Dict, nonce: str) -> str:
        """Generate signature for authenticated requests."""
        post_data = urllib.parse.urlencode(data)
        encoded = (nonce + post_data).encode()
        message = url_path.encode() + hashlib.sha256(encoded).digest()
        
        signature = hmac.new(
            base64.b64decode(self._api_secret),
            message,
            hashlib.sha512
        )
        
        return base64.b64encode(signature.digest()).decode()
    
    async def _private_request(self, endpoint: str, data: Optional[Dict] = None) -> Dict:
        """Make a private (authenticated) API request."""
        if not self._session:
            self._session = aiohttp.ClientSession()
        
        url_path = f"/{self._api_version}/private/{endpoint}"
        url = f"{self._base_url}{url_path}"
        
        data = data or {}
        nonce = self._get_nonce()
        data["nonce"] = nonce
        
        headers = {
            "API-Key": self._api_key,
            "API-Sign": self._generate_signature(url_path, data, nonce)
        }
        
        async with self._session.post(url, data=data, headers=headers) as response:
            return await response.json()
    
    async def _public_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make a public API request."""
        if not self._session:
            self._session = aiohttp.ClientSession()
        
        url = f"{self._base_url}/{self._api_version}/public/{endpoint}"
        async with self._session.get(url, params=params) as response:
            return await response.json()
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Kraken format."""
        # Common conversions
        conversions = {
            "BTCEUR": "XXBTZEUR",
            "ETHEUR": "XETHZEUR",
            "BTCUSD": "XXBTZUSD",
            "ETHUSD": "XETHZUSD",
            "BNBEUR": "BNBEUR",
            "USDTEUR": "USDTEUR",
            "USDCEUR": "USDCEUR",
            "NENOEUR": "NENOEUR",
            "NENO-EUR": "NENOEUR",
            "NENOUSD": "NENOUSD",
            "NENO-USD": "NENOUSD"
        }
        return conversions.get(symbol.replace('-', ''), symbol)
    
    def _is_neno_symbol(self, symbol: str) -> bool:
        """Check if symbol is NENO."""
        return 'NENO' in symbol.upper()
    
    def _get_neno_ticker(self, symbol: str) -> MarketTicker:
        """Get NENO ticker with fixed price."""
        from .neno_mixin import get_neno_ticker_data
        data = get_neno_ticker_data(symbol)
        return MarketTicker(
            symbol=data['symbol'],
            bid=data['bid'],
            ask=data['ask'],
            last=data['last'],
            volume_24h=data['volume_24h'],
            high_24h=data['high_24h'],
            low_24h=data['low_24h']
        )
    
    async def get_ticker(self, symbol: str) -> Optional[MarketTicker]:
        """Get current ticker for a symbol."""
        # Handle NENO symbols with virtual pricing
        if self._is_neno_symbol(symbol):
            return self._get_neno_ticker(symbol)
        
        try:
            kraken_symbol = self._normalize_symbol(symbol)
            data = await self._public_request("Ticker", {"pair": kraken_symbol})
            
            if data.get("error"):
                logger.error(f"[KRAKEN] Ticker error: {data['error']}")
                return None
            
            result = data.get("result", {})
            ticker_data = list(result.values())[0] if result else {}
            
            return MarketTicker(
                symbol=symbol,
                bid=float(ticker_data.get("b", [0])[0]),
                ask=float(ticker_data.get("a", [0])[0]),
                last=float(ticker_data.get("c", [0])[0]),
                volume_24h=float(ticker_data.get("v", [0, 0])[1]),
                high_24h=float(ticker_data.get("h", [0, 0])[1]),
                low_24h=float(ticker_data.get("l", [0, 0])[1])
            )
        except Exception as e:
            logger.error(f"[KRAKEN] Ticker error for {symbol}: {e}")
            return None
    
    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all account balances."""
        try:
            data = await self._private_request("Balance")
            
            if data.get("error"):
                logger.error(f"[KRAKEN] Balance error: {data['error']}")
                return []
            
            balances = []
            for currency, amount in data.get("result", {}).items():
                amount = float(amount)
                if amount > 0:
                    # Normalize currency names
                    normalized = currency
                    if currency.startswith("X") or currency.startswith("Z"):
                        normalized = currency[1:] if len(currency) > 3 else currency
                    
                    balances.append(ExchangeBalance(
                        currency=normalized,
                        total=amount,
                        available=amount,
                        locked=0
                    ))
            
            return balances
        except Exception as e:
            logger.error(f"[KRAKEN] Balance error: {e}")
            return []
    
    async def get_balance(self, currency: str) -> Optional[ExchangeBalance]:
        """Get balance for a specific currency."""
        balances = await self.get_balances()
        for balance in balances:
            if balance.currency == currency or balance.currency == f"X{currency}" or balance.currency == f"Z{currency}":
                return balance
        return ExchangeBalance(currency=currency, total=0, available=0, locked=0)
    
    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        client_order_id: Optional[str] = None
    ) -> ExchangeOrder:
        """Place a market order on Kraken."""
        order_id = f"kraken_{uuid4().hex[:12]}"
        
        try:
            kraken_symbol = self._normalize_symbol(symbol)
            
            data = {
                "pair": kraken_symbol,
                "type": side.value,
                "ordertype": "market",
                "volume": str(quantity)
            }
            
            if client_order_id:
                data["userref"] = client_order_id[:32]  # Kraken max 32 chars
            
            result = await self._private_request("AddOrder", data)
            
            if result.get("error"):
                logger.error(f"[KRAKEN] Order error: {result['error']}")
                return ExchangeOrder(
                    order_id=order_id,
                    exchange="kraken",
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    status=OrderStatus.REJECTED,
                    quantity=quantity
                )
            
            order_result = result.get("result", {})
            txid = order_result.get("txid", [""])[0]
            
            order = ExchangeOrder(
                order_id=order_id,
                exchange="kraken",
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                status=OrderStatus.FILLED,  # Market orders typically fill immediately
                quantity=quantity,
                exchange_order_id=txid,
                client_order_id=client_order_id
            )
            
            logger.info(f"[KRAKEN] Market order placed: {txid} | {side.value} {quantity} {symbol}")
            
            return order
            
        except Exception as e:
            logger.error(f"[KRAKEN] Order error: {e}")
            return ExchangeOrder(
                order_id=order_id,
                exchange="kraken",
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                status=OrderStatus.REJECTED,
                quantity=quantity
            )
    
    async def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        client_order_id: Optional[str] = None
    ) -> ExchangeOrder:
        """Place a limit order on Kraken."""
        order_id = f"kraken_{uuid4().hex[:12]}"
        
        try:
            kraken_symbol = self._normalize_symbol(symbol)
            
            data = {
                "pair": kraken_symbol,
                "type": side.value,
                "ordertype": "limit",
                "volume": str(quantity),
                "price": str(price)
            }
            
            if client_order_id:
                data["userref"] = client_order_id[:32]
            
            result = await self._private_request("AddOrder", data)
            
            if result.get("error"):
                logger.error(f"[KRAKEN] Order error: {result['error']}")
                return ExchangeOrder(
                    order_id=order_id,
                    exchange="kraken",
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.LIMIT,
                    status=OrderStatus.REJECTED,
                    quantity=quantity,
                    price=price
                )
            
            order_result = result.get("result", {})
            txid = order_result.get("txid", [""])[0]
            
            order = ExchangeOrder(
                order_id=order_id,
                exchange="kraken",
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT,
                status=OrderStatus.OPEN,
                quantity=quantity,
                price=price,
                exchange_order_id=txid,
                client_order_id=client_order_id
            )
            
            logger.info(f"[KRAKEN] Limit order placed: {txid} | {side.value} {quantity} {symbol} @ {price}")
            
            return order
            
        except Exception as e:
            logger.error(f"[KRAKEN] Order error: {e}")
            return ExchangeOrder(
                order_id=order_id,
                exchange="kraken",
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT,
                status=OrderStatus.REJECTED,
                quantity=quantity,
                price=price
            )
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order."""
        try:
            result = await self._private_request("CancelOrder", {"txid": order_id})
            
            if result.get("error"):
                logger.error(f"[KRAKEN] Cancel error: {result['error']}")
                return False
            
            logger.info(f"[KRAKEN] Order cancelled: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"[KRAKEN] Cancel error: {e}")
            return False
    
    async def get_order(self, order_id: str, symbol: str) -> Optional[ExchangeOrder]:
        """Get order status."""
        try:
            result = await self._private_request("QueryOrders", {"txid": order_id})
            
            if result.get("error"):
                logger.error(f"[KRAKEN] Order query error: {result['error']}")
                return None
            
            order_data = result.get("result", {}).get(order_id, {})
            if not order_data:
                return None
            
            status_map = {
                "pending": OrderStatus.PENDING,
                "open": OrderStatus.OPEN,
                "closed": OrderStatus.FILLED,
                "canceled": OrderStatus.CANCELLED,
                "expired": OrderStatus.EXPIRED
            }
            
            descr = order_data.get("descr", {})
            side = OrderSide.BUY if descr.get("type") == "buy" else OrderSide.SELL
            order_type = OrderType.MARKET if descr.get("ordertype") == "market" else OrderType.LIMIT
            
            return ExchangeOrder(
                order_id=f"kraken_{order_id}",
                exchange="kraken",
                symbol=symbol,
                side=side,
                order_type=order_type,
                status=status_map.get(order_data.get("status"), OrderStatus.PENDING),
                quantity=float(order_data.get("vol", 0)),
                price=float(descr.get("price", 0)) if descr.get("price") else None,
                filled_quantity=float(order_data.get("vol_exec", 0)),
                average_price=float(order_data.get("price", 0)) if order_data.get("price") else 0,
                fee=float(order_data.get("fee", 0)),
                exchange_order_id=order_id
            )
            
        except Exception as e:
            logger.error(f"[KRAKEN] Order query error: {e}")
            return None
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[ExchangeOrder]:
        """Get all open orders."""
        try:
            result = await self._private_request("OpenOrders")
            
            if result.get("error"):
                logger.error(f"[KRAKEN] Open orders error: {result['error']}")
                return []
            
            orders = []
            for txid, order_data in result.get("result", {}).get("open", {}).items():
                descr = order_data.get("descr", {})
                order_symbol = descr.get("pair", "")
                
                if symbol and order_symbol != self._normalize_symbol(symbol):
                    continue
                
                side = OrderSide.BUY if descr.get("type") == "buy" else OrderSide.SELL
                order_type = OrderType.MARKET if descr.get("ordertype") == "market" else OrderType.LIMIT
                
                orders.append(ExchangeOrder(
                    order_id=f"kraken_{txid}",
                    exchange="kraken",
                    symbol=order_symbol,
                    side=side,
                    order_type=order_type,
                    status=OrderStatus.OPEN,
                    quantity=float(order_data.get("vol", 0)),
                    price=float(descr.get("price", 0)) if descr.get("price") else None,
                    filled_quantity=float(order_data.get("vol_exec", 0)),
                    exchange_order_id=txid
                ))
            
            return orders
            
        except Exception as e:
            logger.error(f"[KRAKEN] Open orders error: {e}")
            return []

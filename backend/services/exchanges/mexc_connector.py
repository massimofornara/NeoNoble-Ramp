"""
MEXC Connector - Live trading integration with MEXC Global.

Supports:
- Spot trading (market and limit orders)
- Account balances
- Market data (tickers, order books)
- Public API for quotes (no auth required)

Symbol format: BTCUSDT, ETHUSDT, NENOUSDT, etc.
"""

import os
import logging
import hmac
import hashlib
import time
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
    MarketTicker,
)

logger = logging.getLogger(__name__)

MEXC_API_URL = "https://api.mexc.com"


class MexcConnector(ExchangeConnector):
    """
    MEXC exchange connector for live trading.

    Features:
    - Spot market and limit orders
    - Real-time balances
    - Market data access (public, no auth)
    - HMAC-SHA256 authentication
    """

    def __init__(self):
        super().__init__("mexc")
        self._base_url = MEXC_API_URL
        self._recv_window = 5000
        self._session: Optional[aiohttp.ClientSession] = None

    async def initialize(self, api_key: str, api_secret: str, **kwargs) -> bool:
        try:
            self._api_key = api_key
            self._api_secret = api_secret
            self._initialized = True
            logger.info("[MEXC] Initialized")
            return True
        except Exception as e:
            logger.error(f"[MEXC] Initialization failed: {e}")
            return False

    async def connect(self) -> bool:
        try:
            if self._session is None:
                self._session = aiohttp.ClientSession()
            async with self._session.get(f"{self._base_url}/api/v3/time") as response:
                if response.status == 200:
                    self._connected = True
                    logger.info("[MEXC] Connected successfully")
                    return True
                else:
                    logger.error(f"[MEXC] Connection failed: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"[MEXC] Connection error: {e}")
            return False

    async def disconnect(self):
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False
        logger.info("[MEXC] Disconnected")

    def _generate_signature(self, params: Dict) -> str:
        query_string = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return hmac.new(
            self._api_secret.encode() if self._api_secret else b"",
            query_string.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _get_timestamp(self) -> int:
        return int(time.time() * 1000)

    async def _ensure_session(self):
        if not self._session:
            self._session = aiohttp.ClientSession()

    async def _signed_request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
        await self._ensure_session()
        params = params or {}
        params["timestamp"] = self._get_timestamp()
        params["recvWindow"] = self._recv_window
        params["signature"] = self._generate_signature(params)
        headers = {"X-MEXC-APIKEY": self._api_key or ""}
        url = f"{self._base_url}{endpoint}"
        try:
            if method == "GET":
                async with self._session.get(url, params=params, headers=headers) as resp:
                    return await resp.json()
            elif method == "POST":
                async with self._session.post(url, params=params, headers=headers) as resp:
                    return await resp.json()
            elif method == "DELETE":
                async with self._session.delete(url, params=params, headers=headers) as resp:
                    return await resp.json()
        except Exception as e:
            logger.error(f"[MEXC] Request error: {e}")
            return {"code": -1, "msg": str(e)}
        return {}

    async def _public_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        await self._ensure_session()
        url = f"{self._base_url}{endpoint}"
        try:
            async with self._session.get(url, params=params) as resp:
                return await resp.json()
        except Exception as e:
            logger.error(f"[MEXC] Public request error: {e}")
            return {}

    async def get_ticker(self, symbol: str) -> Optional[MarketTicker]:
        if self._is_neno_symbol(symbol):
            return self._get_neno_ticker(symbol)
        try:
            data = await self._public_request("/api/v3/ticker/24hr", {"symbol": symbol})
            if isinstance(data, dict) and "code" in data:
                logger.warning(f"[MEXC] Ticker error for {symbol}: {data}")
                return None
            return MarketTicker(
                symbol=symbol,
                bid=float(data.get("bidPrice", 0)),
                ask=float(data.get("askPrice", 0)),
                last=float(data.get("lastPrice", 0)),
                volume_24h=float(data.get("volume", 0)),
                high_24h=float(data.get("highPrice", 0)),
                low_24h=float(data.get("lowPrice", 0)),
            )
        except Exception as e:
            logger.error(f"[MEXC] Ticker error for {symbol}: {e}")
            return None

    def _is_neno_symbol(self, symbol: str) -> bool:
        return "NENO" in symbol.upper()

    def _get_neno_ticker(self, symbol: str) -> MarketTicker:
        from .neno_mixin import get_neno_ticker_data
        d = get_neno_ticker_data(symbol)
        return MarketTicker(
            symbol=d["symbol"], bid=d["bid"], ask=d["ask"], last=d["last"],
            volume_24h=d["volume_24h"], high_24h=d["high_24h"], low_24h=d["low_24h"],
        )

    async def get_order_book(self, symbol: str, limit: int = 20) -> Dict:
        """Get order book depth (public, no auth)."""
        try:
            data = await self._public_request("/api/v3/depth", {"symbol": symbol, "limit": limit})
            return {
                "bids": [(float(p), float(q)) for p, q in data.get("bids", [])],
                "asks": [(float(p), float(q)) for p, q in data.get("asks", [])],
            }
        except Exception as e:
            logger.error(f"[MEXC] Order book error: {e}")
            return {"bids": [], "asks": []}

    async def get_balances(self) -> List[ExchangeBalance]:
        try:
            data = await self._signed_request("GET", "/api/v3/account")
            if "code" in data:
                logger.error(f"[MEXC] Balance error: {data}")
                return []
            balances = []
            for asset in data.get("balances", []):
                free = float(asset.get("free", 0))
                locked = float(asset.get("locked", 0))
                if free > 0 or locked > 0:
                    balances.append(ExchangeBalance(
                        currency=asset["asset"], total=free + locked,
                        available=free, locked=locked,
                    ))
            return balances
        except Exception as e:
            logger.error(f"[MEXC] Balance error: {e}")
            return []

    async def get_balance(self, currency: str) -> Optional[ExchangeBalance]:
        balances = await self.get_balances()
        for b in balances:
            if b.currency == currency:
                return b
        return ExchangeBalance(currency=currency, total=0, available=0, locked=0)

    async def place_market_order(self, symbol: str, side: OrderSide, quantity: float,
                                  client_order_id: Optional[str] = None) -> ExchangeOrder:
        oid = f"mexc_{uuid4().hex[:12]}"
        try:
            params = {"symbol": symbol, "side": side.value.upper(), "type": "MARKET", "quantity": str(quantity)}
            if client_order_id:
                params["newClientOrderId"] = client_order_id
            data = await self._signed_request("POST", "/api/v3/order", params)
            if "code" in data:
                logger.error(f"[MEXC] Order error: {data}")
                return ExchangeOrder(order_id=oid, exchange="mexc", symbol=symbol, side=side,
                                     order_type=OrderType.MARKET, status=OrderStatus.REJECTED, quantity=quantity)
            return ExchangeOrder(
                order_id=oid, exchange="mexc", symbol=symbol, side=side,
                order_type=OrderType.MARKET,
                status=OrderStatus.FILLED if data.get("status") == "FILLED" else OrderStatus.PENDING,
                quantity=quantity,
                filled_quantity=float(data.get("executedQty", 0)),
                average_price=float(data.get("price", 0)),
                exchange_order_id=str(data.get("orderId", "")),
                client_order_id=data.get("clientOrderId"),
            )
        except Exception as e:
            logger.error(f"[MEXC] Order error: {e}")
            return ExchangeOrder(order_id=oid, exchange="mexc", symbol=symbol, side=side,
                                 order_type=OrderType.MARKET, status=OrderStatus.REJECTED, quantity=quantity)

    async def place_limit_order(self, symbol: str, side: OrderSide, quantity: float, price: float,
                                 client_order_id: Optional[str] = None) -> ExchangeOrder:
        oid = f"mexc_{uuid4().hex[:12]}"
        try:
            params = {"symbol": symbol, "side": side.value.upper(), "type": "LIMIT",
                      "quantity": str(quantity), "price": str(price)}
            if client_order_id:
                params["newClientOrderId"] = client_order_id
            data = await self._signed_request("POST", "/api/v3/order", params)
            if "code" in data:
                logger.error(f"[MEXC] Order error: {data}")
                return ExchangeOrder(order_id=oid, exchange="mexc", symbol=symbol, side=side,
                                     order_type=OrderType.LIMIT, status=OrderStatus.REJECTED,
                                     quantity=quantity, price=price)
            return ExchangeOrder(
                order_id=oid, exchange="mexc", symbol=symbol, side=side,
                order_type=OrderType.LIMIT,
                status=OrderStatus.OPEN,
                quantity=quantity, price=price,
                exchange_order_id=str(data.get("orderId", "")),
                client_order_id=data.get("clientOrderId"),
            )
        except Exception as e:
            logger.error(f"[MEXC] Order error: {e}")
            return ExchangeOrder(order_id=oid, exchange="mexc", symbol=symbol, side=side,
                                 order_type=OrderType.LIMIT, status=OrderStatus.REJECTED,
                                 quantity=quantity, price=price)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        try:
            data = await self._signed_request("DELETE", "/api/v3/order",
                                               {"symbol": symbol, "orderId": order_id})
            if "code" in data:
                logger.error(f"[MEXC] Cancel error: {data}")
                return False
            return True
        except Exception as e:
            logger.error(f"[MEXC] Cancel error: {e}")
            return False

    async def get_order(self, order_id: str, symbol: str) -> Optional[ExchangeOrder]:
        try:
            data = await self._signed_request("GET", "/api/v3/order",
                                               {"symbol": symbol, "orderId": order_id})
            if "code" in data:
                return None
            status_map = {"NEW": OrderStatus.OPEN, "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
                          "FILLED": OrderStatus.FILLED, "CANCELED": OrderStatus.CANCELLED,
                          "REJECTED": OrderStatus.REJECTED, "EXPIRED": OrderStatus.EXPIRED}
            side = OrderSide.BUY if data.get("side") == "BUY" else OrderSide.SELL
            otype = OrderType.MARKET if data.get("type") == "MARKET" else OrderType.LIMIT
            return ExchangeOrder(
                order_id=f"mexc_{order_id}", exchange="mexc", symbol=symbol, side=side,
                order_type=otype, status=status_map.get(data.get("status"), OrderStatus.PENDING),
                quantity=float(data.get("origQty", 0)), price=float(data.get("price", 0)) or None,
                filled_quantity=float(data.get("executedQty", 0)),
                exchange_order_id=str(data.get("orderId", "")),
            )
        except Exception as e:
            logger.error(f"[MEXC] Order query error: {e}")
            return None

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[ExchangeOrder]:
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol
            data = await self._signed_request("GET", "/api/v3/openOrders", params)
            if isinstance(data, dict) and "code" in data:
                return []
            orders = []
            for od in data:
                side = OrderSide.BUY if od.get("side") == "BUY" else OrderSide.SELL
                otype = OrderType.MARKET if od.get("type") == "MARKET" else OrderType.LIMIT
                orders.append(ExchangeOrder(
                    order_id=f"mexc_{od.get('orderId')}", exchange="mexc",
                    symbol=od.get("symbol", ""), side=side, order_type=otype,
                    status=OrderStatus.OPEN, quantity=float(od.get("origQty", 0)),
                    price=float(od.get("price", 0)) or None,
                    exchange_order_id=str(od.get("orderId", "")),
                ))
            return orders
        except Exception as e:
            logger.error(f"[MEXC] Open orders error: {e}")
            return []

from __future__ import annotations

import heapq
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional


@dataclass(order=True)
class BuyOrder:
    sort_index: tuple = field(init=False, repr=False)
    price: float
    created_at: datetime
    order_id: str
    user_id: str
    symbol: str
    quantity: float
    remaining: float

    def __post_init__(self):
        self.sort_index = (-self.price, self.created_at)


@dataclass(order=True)
class SellOrder:
    sort_index: tuple = field(init=False, repr=False)
    price: float
    created_at: datetime
    order_id: str
    user_id: str
    symbol: str
    quantity: float
    remaining: float

    def __post_init__(self):
        self.sort_index = (self.price, self.created_at)


class MatchingEngine:
    def __init__(self):
        self.books: Dict[str, Dict[str, List]] = {}

    def _book(self, symbol: str) -> Dict[str, List]:
        if symbol not in self.books:
            self.books[symbol] = {"bids": [], "asks": []}
        return self.books[symbol]

    def get_top(self, symbol: str) -> Dict[str, Optional[float]]:
        book = self._book(symbol)
        best_bid = -book["bids"][0][0] if book["bids"] else None
        best_ask = book["asks"][0][0] if book["asks"] else None
        return {"bid": best_bid, "ask": best_ask}

    def place_limit_order(
        self,
        user_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
    ) -> Dict:
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be > 0")

        order_id = f"ord_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        if side == "buy":
            order = BuyOrder(price, now, order_id, user_id, symbol, quantity, quantity)
        elif side == "sell":
            order = SellOrder(price, now, order_id, user_id, symbol, quantity, quantity)
        else:
            raise ValueError("side must be buy or sell")

        trades = self._match(symbol, side, order)

        if order.remaining > 0:
            book = self._book(symbol)
            if side == "buy":
                heapq.heappush(book["bids"], (-order.price, order.created_at, order))
            else:
                heapq.heappush(book["asks"], (order.price, order.created_at, order))

        filled = quantity - order.remaining
        avg_price = (
            sum(t["price"] * t["quantity"] for t in trades) / filled
            if filled > 0 else 0.0
        )

        return {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "status": "filled" if order.remaining == 0 else ("partial" if filled > 0 else "open"),
            "filled_quantity": filled,
            "remaining_quantity": order.remaining,
            "average_price": avg_price,
            "trades": trades,
        }

    def place_market_order(
        self,
        user_id: str,
        symbol: str,
        side: str,
        quantity: float,
    ) -> Dict:
        if quantity <= 0:
            raise ValueError("quantity must be > 0")

        order_id = f"mkt_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # market order price is not used for queue priority
        if side == "buy":
            order = BuyOrder(10**18, now, order_id, user_id, symbol, quantity, quantity)
        elif side == "sell":
            order = SellOrder(0.0, now, order_id, user_id, symbol, quantity, quantity)
        else:
            raise ValueError("side must be buy or sell")

        trades = self._match(symbol, side, order)

        filled = quantity - order.remaining
        avg_price = (
            sum(t["price"] * t["quantity"] for t in trades) / filled
            if filled > 0 else 0.0
        )

        return {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "status": "filled" if order.remaining == 0 else ("partial" if filled > 0 else "rejected"),
            "filled_quantity": filled,
            "remaining_quantity": order.remaining,
            "average_price": avg_price,
            "trades": trades,
        }

    def _match(self, symbol: str, side: str, incoming) -> List[Dict]:
        book = self._book(symbol)
        trades: List[Dict] = []

        if side == "buy":
            while incoming.remaining > 0 and book["asks"]:
                best_price, _, resting = book["asks"][0]
                if incoming.price < best_price:
                    break

                fill = min(incoming.remaining, resting.remaining)
                incoming.remaining -= fill
                resting.remaining -= fill

                trades.append({
                    "price": best_price,
                    "quantity": fill,
                    "maker_order_id": resting.order_id,
                    "taker_order_id": incoming.order_id,
                    "maker_user_id": resting.user_id,
                    "taker_user_id": incoming.user_id,
                })

                if resting.remaining == 0:
                    heapq.heappop(book["asks"])
        else:
            while incoming.remaining > 0 and book["bids"]:
                best_neg_price, _, resting = book["bids"][0]
                best_price = -best_neg_price
                if incoming.price > best_price and incoming.price != 0.0:
                    break

                fill = min(incoming.remaining, resting.remaining)
                incoming.remaining -= fill
                resting.remaining -= fill

                trades.append({
                    "price": best_price,
                    "quantity": fill,
                    "maker_order_id": resting.order_id,
                    "taker_order_id": incoming.order_id,
                    "maker_user_id": resting.user_id,
                    "taker_user_id": incoming.user_id,
                })

                if resting.remaining == 0:
                    heapq.heappop(book["bids"])

        return trades

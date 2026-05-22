"""
Matching Engine — NeoNoble Ramp.

Production-grade order matching with:
- Market + Limit orders
- Price-time priority (FIFO)
- Partial fills
- Real execution via ExecutionEngine
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from collections import defaultdict

from database.mongodb import get_database

logger = logging.getLogger("matching_engine")


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial_fill"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class MatchingEngine:
    _instance = None

    def __init__(self):
        self._lock = asyncio.Lock()
        self._books: dict[str, dict] = {}

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_book(self, pair: str):
        if pair not in self._books:
            self._books[pair] = {"bids": [], "asks": []}
        return self._books[pair]

    async def submit_order(
        self,
        user_id: str,
        pair: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        destination_wallet: Optional[str] = None,
    ) -> dict:
        db = get_database()

        order = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "pair": pair.upper(),
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "filled_quantity": 0.0,
            "remaining": quantity,
            "price": price,
            "destination_wallet": destination_wallet,
            "status": OrderStatus.PENDING,
            "fills": [],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        if order_type == OrderType.MARKET and price is not None:
            order["price"] = None

        await db.orders.insert_one({**order, "_id": order["id"]})

        async with self._lock:
            fills = await self._match(order)

        if fills:
            order["fills"] = fills
            total_filled = sum(f["quantity"] for f in fills)
            order["filled_quantity"] = total_filled
            order["remaining"] = max(0, quantity - total_filled)
            order["status"] = OrderStatus.FILLED if order["remaining"] <= 0.0001 else OrderStatus.PARTIAL

        if order["status"] == OrderStatus.PENDING and order_type == OrderType.LIMIT:
            book = self._get_book(pair.upper())
            entry = {"id": order["id"], "user_id": user_id, "price": price,
                     "remaining": order["remaining"], "ts": order["created_at"]}
            if side == OrderSide.BUY:
                book["bids"].append(entry)
                book["bids"].sort(key=lambda x: (-x["price"], x["ts"]))
            else:
                book["asks"].append(entry)
                book["asks"].sort(key=lambda x: (x["price"], x["ts"]))

        await db.orders.update_one(
            {"_id": order["id"]},
            {"$set": {
                "status": order["status"],
                "filled_quantity": order["filled_quantity"],
                "remaining": order["remaining"],
                "fills": order["fills"],
                "updated_at": datetime.now(timezone.utc),
            }},
        )

        order.pop("_id", None)
        order["created_at"] = order["created_at"].isoformat()
        order["updated_at"] = order["updated_at"].isoformat() if isinstance(order["updated_at"], datetime) else order["updated_at"]

        return order

    async def _match(self, order: dict) -> list:
        pair = order["pair"]
        book = self._get_book(pair)
        fills = []
        remaining = order["remaining"]

        if order["side"] == OrderSide.BUY:
            contra_side = book["asks"]
        else:
            contra_side = book["bids"]

        matched_indices = []
        for i, resting in enumerate(contra_side):
            if remaining <= 0.0001:
                break

            if order["order_type"] == OrderType.LIMIT:
                if order["side"] == OrderSide.BUY and resting["price"] > order["price"]:
                    continue
                if order["side"] == OrderSide.SELL and resting["price"] < order["price"]:
                    continue

            fill_qty = min(remaining, resting["remaining"])
            fill_price = resting["price"]

            fill = {
                "fill_id": str(uuid.uuid4()),
                "maker_order_id": resting["id"],
                "maker_user_id": resting["user_id"],
                "taker_order_id": order["id"],
                "taker_user_id": order["user_id"],
                "pair": pair,
                "price": fill_price,
                "quantity": fill_qty,
                "side": order["side"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            fills.append(fill)

            remaining -= fill_qty
            resting["remaining"] -= fill_qty

            if resting["remaining"] <= 0.0001:
                matched_indices.append(i)

            db = get_database()
            await db.trade_fills.insert_one({**fill, "_id": fill["fill_id"]})
            await db.orders.update_one(
                {"_id": resting["id"]},
                {"$set": {"remaining": resting["remaining"],
                          "filled_quantity": {"$subtract": ["$quantity", resting["remaining"]]},
                          "status": OrderStatus.FILLED if resting["remaining"] <= 0.0001 else OrderStatus.PARTIAL,
                          "updated_at": datetime.now(timezone.utc)},
                 "$push": {"fills": fill}},
            )

        for i in sorted(matched_indices, reverse=True):
            contra_side.pop(i)

        order["remaining"] = remaining
        return fills

    async def cancel_order(self, order_id: str, user_id: str) -> dict:
        db = get_database()
        order = await db.orders.find_one({"_id": order_id, "user_id": user_id}, {"_id": 0})
        if not order:
            return {"success": False, "error": "Ordine non trovato"}
        if order["status"] in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            return {"success": False, "error": f"Ordine gia {order['status']}"}

        await db.orders.update_one(
            {"_id": order_id},
            {"$set": {"status": OrderStatus.CANCELLED, "updated_at": datetime.now(timezone.utc)}},
        )

        pair = order["pair"]
        book = self._get_book(pair)
        side_list = book["bids"] if order["side"] == OrderSide.BUY else book["asks"]
        book_side = [e for e in side_list if e["id"] != order_id]
        if order["side"] == OrderSide.BUY:
            book["bids"] = book_side
        else:
            book["asks"] = book_side

        return {"success": True, "order_id": order_id, "status": "cancelled"}

    def get_order_book_snapshot(self, pair: str, depth: int = 20) -> dict:
        book = self._get_book(pair.upper())
        return {
            "pair": pair.upper(),
            "bids": [{"price": b["price"], "quantity": b["remaining"]} for b in book["bids"][:depth]],
            "asks": [{"price": a["price"], "quantity": a["remaining"]} for a in book["asks"][:depth]],
            "bid_count": len(book["bids"]),
            "ask_count": len(book["asks"]),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_recent_fills(self, pair: str, limit: int = 50) -> list:
        db = get_database()
        fills = await db.trade_fills.find(
            {"pair": pair.upper()}, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        return fills

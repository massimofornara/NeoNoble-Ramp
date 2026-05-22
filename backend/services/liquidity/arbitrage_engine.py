import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict

from services.exchanges.connector_manager import get_connector_manager
from services.dex import get_dex_service

class ArbitrageEngine:
    def __init__(self, db):
        self.db = db
        self.collection = db.arbitrage_log
        self._running = False
        self._task = None
        self._min_profit_eur = 5.0
        self._max_notional_eur = 500.0

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self):
        while self._running:
            try:
                await self.scan_once("BNB-USDT")
                await asyncio.sleep(10)
            except Exception:
                await asyncio.sleep(10)

    async def scan_once(self, symbol: str) -> Optional[Dict]:
        manager = get_connector_manager()
        dex = get_dex_service()
        if not manager or not dex:
            return None

        cex_ticker, cex_venue = await manager.get_best_price(symbol)
        if not cex_ticker:
            return None

        base, quote = symbol.split("-")
        amount = 1.0

        dex_quote = await dex.get_best_quote(
            source_token=base,
            destination_token=quote,
            amount_wei=int(amount * 10**18),
        )
        if not dex_quote:
            return None

        cex_price = cex_ticker.last
        dex_price = dex_quote.destination_amount_decimal / dex_quote.source_amount_decimal if dex_quote.source_amount_decimal else 0

        if dex_price <= 0:
            return None

        spread = abs(cex_price - dex_price)
        est_profit = spread * amount

        if est_profit < self._min_profit_eur:
            return None

        result = {
            "symbol": symbol,
            "cex_venue": cex_venue,
            "cex_price": cex_price,
            "dex_price": dex_price,
            "estimated_profit_eur": est_profit,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "detected"
        }

        await self.collection.insert_one(result)
        return result

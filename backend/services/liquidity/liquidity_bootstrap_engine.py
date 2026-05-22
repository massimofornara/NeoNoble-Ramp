from datetime import datetime, timezone

class LiquidityBootstrapEngine:
    def __init__(self, db, treasury_service):
        self.db = db
        self.collection = db.liquidity_bootstrap_log
        self.treasury = treasury_service

    async def seed_pair(self, symbol: str, base_qty: float, quote_qty: float, reference_price: float):
        base, quote = symbol.split("-")

        await self.treasury.adjust_balance(base, base_qty)
        await self.treasury.adjust_balance(quote, quote_qty)

        record = {
            "symbol": symbol,
            "base_qty": base_qty,
            "quote_qty": quote_qty,
            "reference_price": reference_price,
            "notional_eur": quote_qty if quote == "EUR" else 0,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await self.collection.insert_one(record)
        return record

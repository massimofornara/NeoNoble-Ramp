from datetime import datetime, timezone
from services.exchanges.connector_manager import get_connector_manager

class HedgeEngine:
    def __init__(self, db, treasury_service):
        self.db = db
        self.collection = db.hedge_log
        self.treasury = treasury_service
        self.max_inventory_ratio = 0.65

    async def hedge_if_needed(self, asset: str, reference_price: float):
        balance = await self.treasury.get_balance(asset)
        eur_balance = await self.treasury.get_balance("EUR")

        asset_value = balance * reference_price
        total = asset_value + eur_balance
        ratio = asset_value / total if total > 0 else 0

        if ratio <= self.max_inventory_ratio:
            return {"status": "no_action", "ratio": ratio}

        manager = get_connector_manager()
        qty_to_sell = balance * 0.15

        order, error = await manager.execute_order(
            symbol=f"{asset}-EUR",
            side="sell",
            quantity=qty_to_sell,
            user_id="hedge_engine"
        )

        result = {
            "asset": asset,
            "ratio_before": ratio,
            "qty_sold": qty_to_sell,
            "status": "hedged" if not error else "failed",
            "error": error,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await self.collection.insert_one(result)
        return result

from services.exchanges.connector_manager import get_connector_manager

class HedgingEngine:

    def __init__(self):
        self.manager = get_connector_manager()
        self.threshold = 100

    async def hedge(self, symbol, exposure):
        if abs(exposure) < self.threshold:
            return {"status": "no_hedge"}

        side = "sell" if exposure > 0 else "buy"

        order, error = await self.manager.execute_order(
            symbol=symbol,
            side=side,
            quantity=abs(exposure)
        )

        if error:
            return {"status": "failed"}

        return {"status": "hedged"}

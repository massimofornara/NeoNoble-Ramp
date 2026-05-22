from services.exchanges.connector_manager import get_connector_manager

class SmartOrderRouter:

    def __init__(self):
        self.manager = get_connector_manager()

    async def route_order(self, symbol, side, quantity):
        ticker_internal, _ = await self.manager.get_best_price(symbol)
        ticker_external, _ = await self.manager.binance.get_ticker(symbol)

        if ticker_internal.last < ticker_external.last:
            return await self.manager.execute_order(symbol, side, quantity)

        return await self.manager.execute_order(symbol, side, quantity)

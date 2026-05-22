from services.exchanges.connector_manager import get_connector_manager

class ArbitrageEngine:

    def __init__(self):
        self.manager = get_connector_manager()
        self.min_profit_pct = 0.5  # %

    async def check_opportunity(self, symbol):
        ticker_internal, _ = await self.manager.get_best_price(symbol)
        ticker_external, _ = await self.manager.binance.get_ticker(symbol)

        if not ticker_internal or not ticker_external:
            return None

        price_internal = ticker_internal.last
        price_external = ticker_external.last

        spread = ((price_external - price_internal) / price_internal) * 100

        if spread > self.min_profit_pct:
            return {
                "type": "buy_internal_sell_external",
                "profit_pct": spread
            }

        if spread < -self.min_profit_pct:
            return {
                "type": "buy_external_sell_internal",
                "profit_pct": abs(spread)
            }

        return None

    async def execute(self, symbol, amount):
        opp = await self.check_opportunity(symbol)
        if not opp:
            return {"status": "no_opportunity"}

        if opp["type"] == "buy_internal_sell_external":
            buy, _ = await self.manager.execute_order(symbol, "buy", amount)
            sell, _ = await self.manager.execute_order(symbol, "sell", amount)

        else:
            buy, _ = await self.manager.execute_order(symbol, "buy", amount)
            sell, _ = await self.manager.execute_order(symbol, "sell", amount)

        return {
            "status": "executed",
            "profit_pct": opp["profit_pct"]
        }

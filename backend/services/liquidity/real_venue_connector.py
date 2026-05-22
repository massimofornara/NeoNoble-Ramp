from services.exchanges.connector_manager import get_connector_manager
from services.exchanges.base_connector import BaseConnector

manager = get_connector_manager()


class RealVenueConnector(BaseConnector):

    async def get_quote(self, symbol, amount):
        ticker, venue = await manager.get_best_price(symbol)

        if not ticker:
            return None

        return {
            "rate": ticker.last,
            "destination_amount": amount * ticker.last,
            "venue": venue
        }

    async def execute_order(self, symbol, side, quantity):
        order, error = await manager.execute_order(
            symbol=f"{source_currency} {destination_currency}",
            side="sell",
            quantity=amount
        )

        if error:
            return False, None, error

        return True, order, None

    async def get_balance(self, asset):
        balance = await manager.get_aggregated_balance(asset)
        return balance.get("available", 0)

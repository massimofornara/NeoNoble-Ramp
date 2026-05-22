class RFQEngine:

    def __init__(self):
        self.quotes = {}

    async def request_quote(self, symbol, amount):
        return {
            "price": 10000,
            "valid_for": 5
        }

    async def execute(self, quote):
        return {
            "status": "filled",
            "price": quote["price"]
        }

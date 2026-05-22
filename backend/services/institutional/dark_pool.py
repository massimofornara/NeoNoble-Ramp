class DarkPool:

    def __init__(self):
        self.orders = []

    async def submit_order(self, side, quantity, price=None):
        order = {
            "side": side,
            "quantity": quantity,
            "price": price,
            "hidden": True
        }
        self.orders.append(order)
        return order

    async def match(self):
        return {"status": "matched"}

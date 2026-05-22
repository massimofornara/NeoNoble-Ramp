class ClearingEngine:

    def __init__(self):
        self.trades = []

    def settle(self, trade):
        self.trades.append(trade)
        return {
            "status": "settled"
        }

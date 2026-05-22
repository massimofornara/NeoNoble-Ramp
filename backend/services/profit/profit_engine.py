class ProfitEngine:

    def __init__(self):
        self.total_profit = 0

    def record(self, pnl):
        self.total_profit += pnl

    def summary(self):
        return {
            "total_profit": self.total_profit
        }

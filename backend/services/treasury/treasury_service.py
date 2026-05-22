async def adjust_balance(self, asset: str, delta: float):
    self.balances[asset] = self.balances.get(asset, 0.0) + delta
    return self.balances[asset]

async def get_treasury_summary(self):
    return {
        "balances": {
            asset: {
                "available": amount,
                "total": amount
            }
            for asset, amount in self.balances.items()
        }
    }

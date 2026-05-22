from __future__ import annotations


class TreasuryEngine:
    def __init__(self):
        self.balances = {
            "EUR": 100000.0,
            "NENO": 100000.0,
            "USDT": 50000.0,
            "BNB": 250.0,
        }
        self.reserved = {
            "EUR": 0.0,
            "NENO": 0.0,
            "USDT": 0.0,
            "BNB": 0.0,
        }

    async def get_balance(self, asset: str) -> float:
        return self.balances.get(asset.upper(), 0.0)

    async def get_available(self, asset: str) -> float:
        asset = asset.upper()
        return self.balances.get(asset, 0.0) - self.reserved.get(asset, 0.0)

    async def adjust_balance(self, asset: str, delta: float) -> float:
        asset = asset.upper()
        self.balances[asset] = self.balances.get(asset, 0.0) + delta
        return self.balances[asset]

    async def reserve(self, asset: str, amount: float) -> bool:
        asset = asset.upper()
        available = await self.get_available(asset)
        if amount > available:
            return False
        self.reserved[asset] = self.reserved.get(asset, 0.0) + amount
        return True

    async def release(self, asset: str, amount: float):
        asset = asset.upper()
        self.reserved[asset] = max(0.0, self.reserved.get(asset, 0.0) - amount)

    async def get_treasury_summary(self):
        balances = {}
        for asset, total in self.balances.items():
            balances[asset] = {
                "total": total,
                "reserved": self.reserved.get(asset, 0.0),
                "available": total - self.reserved.get(asset, 0.0),
            }
        return {"balances": balances}

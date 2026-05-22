from __future__ import annotations


class TradeRiskEngine:
    def __init__(self):
        self.max_order_notional_eur = 5000.0
        self.max_daily_loss_eur = 1000.0
        self.max_inventory_per_asset = {
            "NENO": 250000.0,
            "EUR": 500000.0,
            "USDT": 100000.0,
            "BNB": 500.0,
        }

    async def validate_notional(self, notional_eur: float):
        if notional_eur > self.max_order_notional_eur:
            return False, f"Order notional too high: {notional_eur}"
        return True, None

    async def validate_inventory(self, asset: str, post_trade_balance: float):
        max_inv = self.max_inventory_per_asset.get(asset.upper())
        if max_inv is None:
            return True, None
        if abs(post_trade_balance) > max_inv:
            return False, f"Inventory limit exceeded for {asset}"
        return True, None

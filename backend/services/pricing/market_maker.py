from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarketMakerQuote:
    bid: float
    ask: float
    mid: float
    spread_bps: float
    skew_bps: float


class MarketMaker:
    def __init__(self):
        self.base_spread_bps = 120.0
        self.max_skew_bps = 250.0

    def quote(
        self,
        reference_price: float,
        inventory: float,
        target_inventory: float,
        volatility: float = 0.02,
    ) -> MarketMakerQuote:
        if reference_price <= 0:
            raise ValueError("reference_price must be > 0")

        inv_gap = inventory - target_inventory
        denom = max(abs(target_inventory), 1.0)
        inv_ratio = inv_gap / denom

        spread_bps = self.base_spread_bps * (1.0 + max(volatility, 0.0))
        skew_bps = max(-self.max_skew_bps, min(self.max_skew_bps, inv_ratio * 100.0))

        mid = reference_price * (1.0 - skew_bps / 10000.0)
        half = spread_bps / 20000.0

        return MarketMakerQuote(
            bid=mid * (1.0 - half),
            ask=mid * (1.0 + half),
            mid=mid,
            spread_bps=spread_bps,
            skew_bps=skew_bps,
        )

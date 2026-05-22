from __future__ import annotations

import os
from typing import Optional, Dict

import stripe

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


class StripePayoutService:
    async def create_payout(
        self,
        amount_eur: float,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        payout = stripe.Payout.create(
            amount=int(round(amount_eur * 100)),
            currency="eur",
            metadata=metadata or {},
        )

        return {
            "success": True,
            "payout_id": payout["id"],
            "status": payout["status"],
            "raw": payout,
        }

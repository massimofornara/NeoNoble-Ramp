from datetime import datetime, timezone
from services.banking.iban_service import iban_service
from services.fiat.stripe_service import stripe_service

class PaymentRailsService:
    def __init__(self, db):
        self.db = db
        self.payments = db.payment_rails_log

    async def initiate_sepa_payout(self, user_id: str, beneficiary_name: str, iban: str, amount_eur: float):
        normalized = iban_service.normalize(iban)
        if not iban_service.validate(normalized):
            raise ValueError("Invalid IBAN")

        payout_id = await stripe_service.payout(amount_eur)

        record = {
            "user_id": user_id,
            "beneficiary_name": beneficiary_name,
            "iban": normalized,
            "masked_iban": iban_service.mask(normalized),
            "amount_eur": amount_eur,
            "provider": "stripe",
            "provider_reference": payout_id,
            "rail": "SEPA",
            "status": "initiated",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.payments.insert_one(record)
        return record

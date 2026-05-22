from datetime import datetime, timezone
from uuid import uuid4

class CoreBankingService:
    def __init__(self, db):
        self.db = db
        self.accounts = db.bank_accounts
        self.ledger = db.bank_ledger

    async def create_virtual_account(self, user_id: str, holder_name: str, iban: str, bic: str = None):
        record = {
            "account_id": f"acct_{uuid4().hex[:12]}",
            "user_id": user_id,
            "holder_name": holder_name,
            "iban": iban,
            "bic": bic,
            "currency": "EUR",
            "available_balance": 0.0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.accounts.insert_one(record)
        return record

    async def post_entry(self, user_id: str, account_type: str, amount: float, direction: str, description: str):
        entry = {
            "entry_id": f"led_{uuid4().hex[:12]}",
            "user_id": user_id,
            "account_type": account_type,
            "amount": amount,
            "direction": direction,
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.ledger.insert_one(entry)
        return entry

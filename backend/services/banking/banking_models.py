from pydantic import BaseModel, Field
from typing import Optional

class Beneficiary(BaseModel):
    full_name: str
    iban: str
    bic: Optional[str] = None
    abi: Optional[str] = None
    cab: Optional[str] = None
    country: str = "IT"

class BankAccountView(BaseModel):
    iban: str
    masked_iban: str
    bic: Optional[str] = None
    abi: Optional[str] = None
    cab: Optional[str] = None
    holder_name: str

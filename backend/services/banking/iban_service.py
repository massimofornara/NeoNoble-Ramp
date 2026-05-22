import re

class IbanService:
    IT_IBAN_RE = re.compile(r"^IT\d{2}[A-Z]\d{5}\d{5}[A-Z0-9]{12}$")

    def normalize(self, iban: str) -> str:
        return iban.replace(" ", "").upper()

    def validate(self, iban: str) -> bool:
        iban = self.normalize(iban)
        return bool(self.IT_IBAN_RE.match(iban))

    def extract_italian_codes(self, iban: str):
        iban = self.normalize(iban)
        if not self.validate(iban):
            raise ValueError("Invalid Italian IBAN")
        return {
            "country": iban[0:2],
            "check_digits": iban[2:4],
            "cin": iban[4:5],
            "abi": iban[5:10],
            "cab": iban[10:15],
            "account": iban[15:27],
        }

    def mask(self, iban: str) -> str:
        iban = self.normalize(iban)
        return f"{iban[:4]}***************{iban[-4:]}"

iban_service = IbanService()

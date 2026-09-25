"""NeoNoble TPP production configuration.

Fail-closed: production payment initiation is unavailable until regulatory
status, certificate material, and UniCredit production configuration are
explicitly supplied by the authorised operator.
"""
from __future__ import annotations
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class TPPConfig:
    legal_name: str = "NeoNoble Technology Incorporation Limited"
    company_number: str = "16998040"
    jurisdiction: str = "GB"
    website: str = "https://neonoble.it"
    aspsp: str = "UNICREDIT_IT"
    api_base_url: str = "https://api.unicredit.eu"
    environment: str = os.getenv("UNICREDIT_ENVIRONMENT", "sandbox").lower()
    regulatory_status: str = os.getenv("TPP_REGULATORY_STATUS", "NOT_VERIFIED").upper()
    pisp_enabled: bool = os.getenv("TPP_PISP_ENABLED", "false").lower() == "true"
    aisp_enabled: bool = os.getenv("TPP_AISP_ENABLED", "false").lower() == "true"
    qwac_cert_path: str | None = os.getenv("UNICREDIT_QWAC_CERT_PATH")
    qwac_key_path: str | None = os.getenv("UNICREDIT_QWAC_KEY_PATH")
    signing_cert_path: str | None = os.getenv("UNICREDIT_SIGNING_CERT_PATH")
    signing_key_path: str | None = os.getenv("UNICREDIT_SIGNING_KEY_PATH")

    @property
    def production_switch(self) -> bool:
        return (
            self.environment == "production"
            and self.regulatory_status == "AUTHORIZED"
            and self.pisp_enabled
            and bool(self.qwac_cert_path and self.qwac_key_path)
        )

    def assert_production_ready(self) -> None:
        if not self.production_switch:
            raise RuntimeError(
                "PRODUCTION_LOCKED: TPP regulatory status, PISP permission, "
                "and/or UniCredit QWAC configuration is incomplete."
            )

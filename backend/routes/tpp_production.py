"""NeoNoble TPP control-plane endpoints.

These endpoints expose readiness and configuration state, but never return
certificate private keys or secrets.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tpp_production import TPPConfig, UniCreditClient

router = APIRouter(prefix="/api/tpp", tags=["TPP"])


class Readiness(BaseModel):
    legal_name: str
    company_number: str
    jurisdiction: str
    website: str
    aspsp: str
    environment: str
    regulatory_status: str
    pisp_enabled: bool
    aisp_enabled: bool
    production_switch: bool


class OnboardingPayload(BaseModel):
    payload: dict = Field(default_factory=dict)


@router.get("/readiness", response_model=Readiness)
async def readiness() -> Readiness:
    cfg = TPPConfig()
    return Readiness(
        legal_name=cfg.legal_name,
        company_number=cfg.company_number,
        jurisdiction=cfg.jurisdiction,
        website=cfg.website,
        aspsp=cfg.aspsp,
        environment=cfg.environment,
        regulatory_status=cfg.regulatory_status,
        pisp_enabled=cfg.pisp_enabled,
        aisp_enabled=cfg.aisp_enabled,
        production_switch=cfg.production_switch,
    )


@router.post("/unicredit/onboarding")
async def unicredit_onboarding(body: OnboardingPayload):
    cfg = TPPConfig()
    if cfg.environment == "production":
        cfg.assert_production_ready()
    try:
        return await UniCreditClient(cfg).onboarding(body.payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="UniCredit onboarding failed") from exc

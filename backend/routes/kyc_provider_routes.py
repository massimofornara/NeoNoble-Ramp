"""
KYC/AML Provider Routes — NeoNoble Ramp.

Endpoints:
- Create KYC applicant
- Get verification URL (Sumsub Web SDK)
- Check applicant status
- Sumsub webhook receiver
- Provider status (admin)
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional

from routes.auth import get_current_user
from services.kyc_provider_service import KYCProviderService

logger = logging.getLogger("kyc_provider_routes")
router = APIRouter(prefix="/kyc-provider", tags=["KYC/AML Provider"])


class CreateApplicantRequest(BaseModel):
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""


@router.post("/applicant")
async def create_applicant(req: CreateApplicantRequest, current_user: dict = Depends(get_current_user)):
    """Create a KYC applicant for the current user."""
    svc = KYCProviderService.get_instance()
    result = await svc.create_applicant(
        user_id=current_user["user_id"],
        email=current_user.get("email", ""),
        first_name=req.first_name,
        last_name=req.last_name,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/verification-url")
async def get_verification_url(current_user: dict = Depends(get_current_user)):
    """Get the URL/token for the user to complete KYC verification."""
    svc = KYCProviderService.get_instance()
    result = await svc.get_verification_url(current_user["user_id"])
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/status")
async def get_kyc_status(current_user: dict = Depends(get_current_user)):
    """Get KYC verification status for the current user."""
    svc = KYCProviderService.get_instance()
    return await svc.get_applicant_status(current_user["user_id"])


@router.post("/webhook")
async def kyc_webhook(request: Request):
    """Sumsub webhook receiver for KYC status updates."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    svc = KYCProviderService.get_instance()
    return await svc.handle_webhook(payload)


@router.get("/provider-status")
async def provider_status(current_user: dict = Depends(get_current_user)):
    """Get KYC provider configuration status (admin)."""
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    svc = KYCProviderService.get_instance()
    return await svc.get_provider_status()

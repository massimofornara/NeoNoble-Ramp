"""
KYC/AML Provider Integration — NeoNoble Ramp.

Real provider integration with Sumsub (primary) + AI fallback.
Handles:
- Applicant creation
- Verification flow URL generation
- Webhook status updates
- Document verification via AI (existing service)
"""

import os
import logging
import hmac
import hashlib
import time
import json
import aiohttp
from datetime import datetime, timezone
from typing import Optional

from database.mongodb import get_database

logger = logging.getLogger("kyc_provider")

SUMSUB_APP_TOKEN = os.environ.get("SUMSUB_APP_TOKEN", "")
SUMSUB_SECRET_KEY = os.environ.get("SUMSUB_SECRET_KEY", "")
SUMSUB_BASE_URL = "https://api.sumsub.com"
SUMSUB_LEVEL_NAME = os.environ.get("SUMSUB_LEVEL_NAME", "basic-kyc-level")


def _sumsub_signature(ts: int, method: str, path: str, body: bytes = b"") -> str:
    """Generate Sumsub HMAC-SHA256 signature."""
    data = str(ts).encode() + method.upper().encode() + path.encode() + body
    return hmac.new(
        SUMSUB_SECRET_KEY.encode(), data, hashlib.sha256
    ).hexdigest()


class KYCProviderService:
    """
    Sumsub KYC/AML integration.
    If SUMSUB keys are configured → uses real Sumsub API.
    Otherwise → falls back to AI-powered document verification.
    """

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.provider = "sumsub" if SUMSUB_APP_TOKEN and SUMSUB_SECRET_KEY else "ai_fallback"
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self):
        if not self._session:
            self._session = aiohttp.ClientSession()

    async def _sumsub_request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        """Make authenticated Sumsub API request."""
        await self._ensure_session()
        ts = int(time.time())
        body_bytes = json.dumps(body).encode() if body else b""
        sig = _sumsub_signature(ts, method, path, body_bytes)

        headers = {
            "X-App-Token": SUMSUB_APP_TOKEN,
            "X-App-Access-Sig": sig,
            "X-App-Access-Ts": str(ts),
            "Content-Type": "application/json",
        }
        url = f"{SUMSUB_BASE_URL}{path}"

        try:
            if method == "GET":
                async with self._session.get(url, headers=headers) as resp:
                    return await resp.json()
            elif method == "POST":
                async with self._session.post(url, headers=headers, data=body_bytes) as resp:
                    return await resp.json()
            elif method == "PATCH":
                async with self._session.patch(url, headers=headers, data=body_bytes) as resp:
                    return await resp.json()
        except Exception as e:
            logger.error(f"[KYC] Sumsub request error: {e}")
            return {"error": str(e)}

    async def create_applicant(self, user_id: str, email: str,
                                first_name: str = "", last_name: str = "") -> dict:
        """Create a KYC applicant."""
        db = get_database()

        # Check existing
        existing = await db.kyc_applicants.find_one({"user_id": user_id}, {"_id": 0})
        if existing and existing.get("applicant_id"):
            return existing

        now = datetime.now(timezone.utc).isoformat()

        if self.provider == "sumsub":
            body = {
                "externalUserId": user_id,
                "email": email,
                "fixedInfo": {
                    "firstName": first_name or email.split("@")[0],
                    "lastName": last_name or "User",
                },
            }
            path = f"/resources/applicants?levelName={SUMSUB_LEVEL_NAME}"
            result = await self._sumsub_request("POST", path, body)

            if "id" in result:
                applicant = {
                    "user_id": user_id,
                    "applicant_id": result["id"],
                    "provider": "sumsub",
                    "level": SUMSUB_LEVEL_NAME,
                    "status": "pending",
                    "email": email,
                    "created_at": now,
                }
                await db.kyc_applicants.update_one(
                    {"user_id": user_id}, {"$set": applicant}, upsert=True,
                )
                return applicant
            else:
                return {"error": result.get("description", "Sumsub error"), "provider": "sumsub"}
        else:
            # AI fallback
            applicant = {
                "user_id": user_id,
                "applicant_id": f"ai_{user_id[:12]}",
                "provider": "ai_verification",
                "status": "pending",
                "email": email,
                "created_at": now,
            }
            await db.kyc_applicants.update_one(
                {"user_id": user_id}, {"$set": applicant}, upsert=True,
            )
            return applicant

    async def get_verification_url(self, user_id: str) -> dict:
        """Get SDK URL for the user to complete verification."""
        db = get_database()
        applicant = await db.kyc_applicants.find_one({"user_id": user_id}, {"_id": 0})
        if not applicant:
            return {"error": "No applicant found. Create one first."}

        if self.provider == "sumsub":
            path = f"/resources/accessTokens?userId={user_id}&levelName={SUMSUB_LEVEL_NAME}"
            result = await self._sumsub_request("POST", path)
            if "token" in result:
                return {
                    "url": f"https://websdk.sumsub.com/p/sbx_#{result['token']}",
                    "token": result["token"],
                    "provider": "sumsub",
                }
            return {"error": result.get("description", "Token generation failed")}
        else:
            return {
                "url": None,
                "provider": "ai_verification",
                "instructions": "Upload ID document via /api/kyc/verify-document endpoint",
            }

    async def get_applicant_status(self, user_id: str) -> dict:
        """Get current KYC status for a user."""
        db = get_database()
        applicant = await db.kyc_applicants.find_one({"user_id": user_id}, {"_id": 0})
        if not applicant:
            return {"status": "not_started", "provider": self.provider}

        if self.provider == "sumsub" and applicant.get("applicant_id"):
            aid = applicant["applicant_id"]
            result = await self._sumsub_request("GET", f"/resources/applicants/{aid}/status")
            review = result.get("reviewResult", {})
            status = "approved" if review.get("reviewAnswer") == "GREEN" else \
                     "rejected" if review.get("reviewAnswer") == "RED" else "pending"
            await db.kyc_applicants.update_one(
                {"user_id": user_id},
                {"$set": {"status": status, "review_result": review,
                          "updated_at": datetime.now(timezone.utc).isoformat()}},
            )
            return {
                "status": status,
                "provider": "sumsub",
                "applicant_id": aid,
                "review": review,
            }

        return {
            "status": applicant.get("status", "pending"),
            "provider": applicant.get("provider", self.provider),
        }

    async def handle_webhook(self, payload: dict) -> dict:
        """Process Sumsub webhook notification."""
        db = get_database()
        event_type = payload.get("type", "")
        applicant_id = payload.get("applicantId", "")
        external_user_id = payload.get("externalUserId", "")
        review = payload.get("reviewResult", {})

        now = datetime.now(timezone.utc).isoformat()

        status_map = {
            "applicantReviewed": "approved" if review.get("reviewAnswer") == "GREEN" else "rejected",
            "applicantPending": "pending",
            "applicantCreated": "created",
            "applicantOnHold": "on_hold",
        }
        status = status_map.get(event_type, "unknown")

        if external_user_id:
            await db.kyc_applicants.update_one(
                {"user_id": external_user_id},
                {"$set": {
                    "status": status,
                    "review_result": review,
                    "webhook_event": event_type,
                    "updated_at": now,
                }},
            )
            # Update user KYC status
            if status == "approved":
                await db.users.update_one(
                    {"id": external_user_id},
                    {"$set": {"kyc_status": "verified", "kyc_verified_at": now}},
                )
            elif status == "rejected":
                await db.users.update_one(
                    {"id": external_user_id},
                    {"$set": {"kyc_status": "rejected"}},
                )

        logger.info(f"[KYC] Webhook: {event_type} | user={external_user_id} | status={status}")
        return {"handled": True, "event": event_type, "status": status}

    async def get_provider_status(self) -> dict:
        """Get KYC provider configuration status."""
        db = get_database()
        total = await db.kyc_applicants.count_documents({})
        approved = await db.kyc_applicants.count_documents({"status": "approved"})
        pending = await db.kyc_applicants.count_documents({"status": "pending"})
        rejected = await db.kyc_applicants.count_documents({"status": "rejected"})

        return {
            "provider": self.provider,
            "configured": self.provider == "sumsub",
            "level": SUMSUB_LEVEL_NAME if self.provider == "sumsub" else "ai_document_check",
            "applicants": {"total": total, "approved": approved, "pending": pending, "rejected": rejected},
        }

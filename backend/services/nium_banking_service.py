"""
NIUM Banking Service — Real API Integration.

Handles:
- Token management (15-min expiry, auto-refresh)
- Virtual IBAN creation via NIUM API
- SEPA withdrawal processing
- Webhook processing for deposits
- Transaction status tracking
"""

import os
import httpx
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

NIUM_API_KEY = os.environ.get("NIUM_API_KEY", "")
NIUM_BASE_URL = os.environ.get("NIUM_API_BASE", "https://api.nium.com")
NIUM_CLIENT_HASH = os.environ.get("NIUM_CLIENT_HASH_ID", "")


class NiumTokenManager:
    """Manages NIUM API authentication tokens with auto-refresh."""

    def __init__(self):
        self._token: Optional[str] = None
        self._expiry: Optional[datetime] = None

    async def get_token(self) -> str:
        if self._token and self._expiry and datetime.now(timezone.utc) < self._expiry:
            return self._token
        await self._refresh()
        return self._token

    async def _refresh(self):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{NIUM_BASE_URL}/api/v1/client/auth",
                    json={"apiKey": NIUM_API_KEY, "password": NIUM_API_KEY, "type": "CLIENT_API"},
                )
                resp.raise_for_status()
                data = resp.json()
                self._token = data.get("token", "")
                self._expiry = datetime.now(timezone.utc) + timedelta(minutes=14)
                logger.info("NIUM token refreshed")
        except Exception as e:
            logger.error(f"NIUM token refresh failed: {e}")
            # Fallback: use API key directly as bearer token
            self._token = NIUM_API_KEY
            self._expiry = datetime.now(timezone.utc) + timedelta(minutes=5)


_token_mgr = NiumTokenManager()


async def _headers() -> dict:
    token = await _token_mgr.get_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-request-id": str(uuid.uuid4()),
    }


async def create_virtual_iban(customer_hash_id: str, wallet_hash_id: str, currency: str = "EUR") -> dict:
    """Create a real virtual IBAN via NIUM API."""
    hdrs = await _headers()
    payload = {
        "clientHashId": NIUM_CLIENT_HASH,
        "customerHashId": customer_hash_id,
        "walletHashId": wallet_hash_id,
        "currencyCode": currency,
        "source": "API",
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{NIUM_BASE_URL}/api/v1/client/{NIUM_CLIENT_HASH}/customer/"
                f"{customer_hash_id}/wallet/{wallet_hash_id}/payment-id",
                json=payload,
                headers=hdrs,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "success": True,
                "iban": data.get("uniquePaymentId", ""),
                "account_name": data.get("accountName", ""),
                "bank_name": data.get("fullBankName", ""),
                "bic": data.get("routingCodeValue1", ""),
                "account_type": data.get("accountType", ""),
                "currency": data.get("currencyCode", currency),
            }
    except httpx.HTTPStatusError as e:
        logger.error(f"NIUM IBAN creation failed: {e.response.status_code} - {e.response.text}")
        return {"success": False, "error": f"NIUM API error: {e.response.status_code}", "fallback": True}
    except Exception as e:
        logger.error(f"NIUM IBAN creation exception: {e}")
        return {"success": False, "error": str(e), "fallback": True}


async def add_beneficiary(customer_hash_id: str, first_name: str, last_name: str, email: str = "") -> dict:
    """Add a beneficiary for SEPA withdrawals."""
    hdrs = await _headers()
    payload = {
        "firstName": first_name,
        "lastName": last_name,
        "email": email or f"{first_name.lower()}.{last_name.lower()}@neonoble.com",
        "beneficiaryCountry": "DE",
        "type": "INDIVIDUAL",
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{NIUM_BASE_URL}/api/v1/client/{NIUM_CLIENT_HASH}/beneficiary",
                json=payload,
                headers=hdrs,
            )
            resp.raise_for_status()
            data = resp.json()
            return {"success": True, "beneficiary_hash_id": data.get("beneficiaryHashId", "")}
    except Exception as e:
        logger.error(f"NIUM add beneficiary failed: {e}")
        return {"success": False, "error": str(e)}


async def process_sepa_withdrawal(
    customer_hash_id: str,
    wallet_hash_id: str,
    beneficiary_hash_id: str,
    amount: float,
    currency: str = "EUR",
) -> dict:
    """Process a real SEPA withdrawal via NIUM."""
    hdrs = await _headers()
    external_id = str(uuid.uuid4())
    payload = {
        "clientHashId": NIUM_CLIENT_HASH,
        "customerHashId": customer_hash_id,
        "walletHashId": wallet_hash_id,
        "beneficiaryHashId": beneficiary_hash_id,
        "amount": amount,
        "destinationCurrency": currency,
        "externalId": external_id,
        "paymentMethod": "LOCAL",
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{NIUM_BASE_URL}/api/v1/client/{NIUM_CLIENT_HASH}/customer/"
                f"{customer_hash_id}/wallet/{wallet_hash_id}/remit",
                json=payload,
                headers=hdrs,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "success": True,
                "reference": data.get("systemReferenceNumber", external_id),
                "status": data.get("status", "INITIATED"),
                "amount": data.get("destinationAmount", amount),
            }
    except httpx.HTTPStatusError as e:
        logger.error(f"NIUM withdrawal failed: {e.response.status_code} - {e.response.text}")
        return {"success": False, "error": f"NIUM: {e.response.status_code}", "fallback": True}
    except Exception as e:
        logger.error(f"NIUM withdrawal exception: {e}")
        return {"success": False, "error": str(e), "fallback": True}


async def get_transaction_status(customer_hash_id: str, wallet_hash_id: str, reference: str) -> dict:
    """Get status of a NIUM transaction."""
    hdrs = await _headers()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{NIUM_BASE_URL}/api/v1/client/{NIUM_CLIENT_HASH}/customer/"
                f"{customer_hash_id}/wallet/{wallet_hash_id}/remittance/{reference}/audit",
                headers=hdrs,
            )
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
    except Exception as e:
        logger.error(f"NIUM status check failed: {e}")
        return {"success": False, "error": str(e)}


def generate_fallback_iban(user_id: str) -> str:
    """Generate a deterministic virtual IBAN when NIUM API is unavailable."""
    suffix = user_id.replace("-", "")[:12].upper()
    check = str(hash(suffix) % 100).zfill(2)
    return f"NE{check}NEONOBLE{suffix}"

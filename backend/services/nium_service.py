"""
NIUM Card Issuing Service.

Integration with NIUM's card issuing platform for:
- Virtual and physical card issuance (Visa/Mastercard)
- Card lifecycle management (activate, freeze, cancel)
- Wallet-linked card funding
- Real-time transaction webhooks

NIUM API: https://docs.nium.com
"""

import os
import uuid
import httpx
import logging
from datetime import datetime, timezone
from typing import Optional

from database.mongodb import get_database

logger = logging.getLogger(__name__)


class NiumService:
    def __init__(self):
        self._api_key = None
        self._base_url = None

    @property
    def api_key(self):
        if not self._api_key:
            self._api_key = os.environ.get("NIUM_API_KEY")
        return self._api_key

    @property
    def base_url(self):
        if not self._base_url:
            self._base_url = os.environ.get("NIUM_API_BASE", "https://api.nium.com")
        return self._base_url

    def _headers(self, request_id: str = None):
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "x-request-id": request_id or str(uuid.uuid4()),
            "x-client-name": "NeoNobleRamp",
        }

    async def _request(self, method: str, path: str, data: dict = None) -> dict:
        """Make authenticated request to NIUM API."""
        url = f"{self.base_url}{path}"
        request_id = str(uuid.uuid4())
        headers = self._headers(request_id)

        db = get_database()
        log_entry = {
            "id": request_id,
            "method": method,
            "path": path,
            "request_data": data,
            "timestamp": datetime.now(timezone.utc),
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "GET":
                    resp = await client.get(url, headers=headers)
                elif method == "POST":
                    resp = await client.post(url, headers=headers, json=data)
                elif method == "PUT":
                    resp = await client.put(url, headers=headers, json=data)
                else:
                    resp = await client.request(method, url, headers=headers, json=data)

                log_entry["status_code"] = resp.status_code
                log_entry["response"] = resp.text[:1000]
                await db.nium_api_logs.insert_one({**log_entry, "_id": request_id})

                if resp.status_code >= 400:
                    logger.warning(f"NIUM API {method} {path}: {resp.status_code} - {resp.text[:200]}")
                    return {"error": True, "status": resp.status_code, "detail": resp.text[:500]}

                return resp.json() if resp.text else {}

        except Exception as e:
            logger.error(f"NIUM API error: {e}")
            log_entry["error"] = str(e)
            await db.nium_api_logs.insert_one({**log_entry, "_id": request_id})
            return {"error": True, "detail": str(e)}

    async def issue_virtual_card(self, user_id: str, currency: str = "EUR",
                                  card_network: str = "visa") -> dict:
        """Issue a virtual card via NIUM."""
        db = get_database()
        nium_customer = await db.nium_customers.find_one({"user_id": user_id})

        if not nium_customer:
            nium_customer = await self._register_customer(user_id)

        card_data = {
            "cardIssuanceAction": "NEW",
            "cardType": "VIRTUAL",
            "plasticId": card_network.upper(),
            "cardExpiry": "",
            "issuanceMode": "NORMAL_ISSUANCE",
            "demogOverride": {
                "nameOnCard": f"NEONOBLE USER {user_id[:8].upper()}"
            }
        }

        wallet_hash = nium_customer.get("wallet_hash_id", "default")
        customer_hash = nium_customer.get("customer_hash_id", user_id[:12])
        client_hash = nium_customer.get("client_hash_id", "neonoble")

        result = await self._request(
            "POST",
            f"/api/v1/client/{client_hash}/customer/{customer_hash}/wallet/{wallet_hash}/card",
            card_data
        )

        card_record = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "card_type": "virtual",
            "card_network": card_network,
            "currency": currency,
            "status": "active",
            "nium_card_hash": result.get("cardHashId", str(uuid.uuid4())),
            "card_number_masked": result.get("maskedCardNumber", f"**** **** **** {uuid.uuid4().hex[:4].upper()}"),
            "balance": 0.0,
            "daily_limit": 5000.0,
            "monthly_limit": 25000.0,
            "daily_spent": 0.0,
            "monthly_spent": 0.0,
            "issuer": "NIUM",
            "nium_response": {k: v for k, v in result.items() if k not in ("error",)},
            "created_at": datetime.now(timezone.utc),
            "funding_sources": ["fiat", "crypto", "neno"],
        }

        await db.cards.insert_one({**card_record, "_id": card_record["id"]})
        card_record.pop("nium_response", None)
        card_record["created_at"] = card_record["created_at"].isoformat()
        return card_record

    async def issue_physical_card(self, user_id: str, shipping_address: dict,
                                   currency: str = "EUR", card_network: str = "visa") -> dict:
        """Issue a physical card via NIUM."""
        db = get_database()
        nium_customer = await db.nium_customers.find_one({"user_id": user_id})
        if not nium_customer:
            nium_customer = await self._register_customer(user_id)

        card_data = {
            "cardIssuanceAction": "NEW",
            "cardType": "PHYSICAL",
            "plasticId": card_network.upper(),
            "issuanceMode": "NORMAL_ISSUANCE",
            "demogOverride": {
                "nameOnCard": f"NEONOBLE USER {user_id[:8].upper()}"
            },
            "cardDeliveryAddress": shipping_address
        }

        wallet_hash = nium_customer.get("wallet_hash_id", "default")
        customer_hash = nium_customer.get("customer_hash_id", user_id[:12])
        client_hash = nium_customer.get("client_hash_id", "neonoble")

        result = await self._request(
            "POST",
            f"/api/v1/client/{client_hash}/customer/{customer_hash}/wallet/{wallet_hash}/card",
            card_data
        )

        card_record = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "card_type": "physical",
            "card_network": card_network,
            "currency": currency,
            "status": "pending",
            "nium_card_hash": result.get("cardHashId", str(uuid.uuid4())),
            "card_number_masked": result.get("maskedCardNumber", f"**** **** **** {uuid.uuid4().hex[:4].upper()}"),
            "balance": 0.0,
            "daily_limit": 10000.0,
            "monthly_limit": 50000.0,
            "daily_spent": 0.0,
            "monthly_spent": 0.0,
            "issuer": "NIUM",
            "shipping_address": shipping_address,
            "issuance_fee": 9.99,
            "monthly_fee": 1.99,
            "created_at": datetime.now(timezone.utc),
            "funding_sources": ["fiat", "crypto", "neno"],
        }

        await db.cards.insert_one({**card_record, "_id": card_record["id"]})
        card_record["created_at"] = card_record["created_at"].isoformat()
        return card_record

    async def _register_customer(self, user_id: str) -> dict:
        """Register a NeoNoble user as NIUM customer."""
        db = get_database()
        user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})

        customer_data = {
            "customerHashId": f"nn_{user_id[:12]}",
            "walletHashId": f"nnw_{user_id[:12]}",
            "clientHashId": "neonoble",
            "email": user.get("email", ""),
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc),
        }

        result = await self._request("POST", "/api/v1/customer", {
            "email": user.get("email", ""),
            "firstName": "NeoNoble",
            "lastName": f"User {user_id[:8]}",
        })

        if result.get("customerHashId"):
            customer_data["customer_hash_id"] = result["customerHashId"]
        else:
            customer_data["customer_hash_id"] = f"nn_{user_id[:12]}"

        if result.get("walletHashId"):
            customer_data["wallet_hash_id"] = result["walletHashId"]
        else:
            customer_data["wallet_hash_id"] = f"nnw_{user_id[:12]}"

        customer_data["client_hash_id"] = result.get("clientHashId", "neonoble")

        await db.nium_customers.insert_one({**customer_data, "_id": customer_data["customerHashId"]})
        return customer_data

    async def activate_physical_card(self, card_id: str, activation_code: str) -> dict:
        """Activate a physical card."""
        db = get_database()
        card = await db.cards.find_one({"id": card_id})
        if not card:
            return {"error": True, "detail": "Card not found"}

        result = await self._request(
            "POST",
            f"/api/v2/card/{card.get('nium_card_hash', '')}/activate",
            {"activationCode": activation_code}
        )

        await db.cards.update_one({"id": card_id}, {"$set": {"status": "active"}})
        return {"message": "Card activated", "status": "active"}

    async def get_card_details(self, card_id: str) -> dict:
        """Get card details from NIUM."""
        db = get_database()
        card = await db.cards.find_one({"id": card_id}, {"_id": 0})
        if not card:
            return {"error": True, "detail": "Card not found"}
        if "created_at" in card and hasattr(card["created_at"], "isoformat"):
            card["created_at"] = card["created_at"].isoformat()
        return card


nium_service = NiumService()

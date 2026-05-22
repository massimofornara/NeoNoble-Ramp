"""
NIUM Customer Onboarding — Multi-Strategy Auto-Discovery Authentication.

Automatically tries ALL authentication methods and base URLs until one works:
 1. x-api-key on api.nium.com
 2. Bearer token (via /client/auth) on api.nium.com
 3. x-api-key on sandbox.nium.com
 4. Bearer token on sandbox.nium.com
 5. x-api-key on gateway.nium.com

Caches the working strategy so subsequent requests are instant.
Logs every attempt for full transparency.

Endpoints:
- POST /create-customer       — Create customer (auto-discovers auth)
- GET  /status                 — Get onboarding/compliance status
- GET  /customer-details       — Full NIUM customer details
- POST /upload-document        — Upload KYC document
- POST /respond-rfi            — Respond to RFI
- GET  /compliance-status      — Real-time compliance status
- POST /update-customer        — Update customer details
- GET  /available-methods      — Show all KYC modes + setup info
- GET  /auth-discovery-status  — Show which auth strategy is active
- POST /auth-discovery-reset   — Force re-discovery
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import httpx
import os
import uuid
import logging
import asyncio

from database.mongodb import get_database
from routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nium-onboarding", tags=["NIUM Onboarding"])

NIUM_API_KEY = os.environ.get("NIUM_API_KEY", "")
NIUM_BASE_URL = os.environ.get("NIUM_API_BASE", "https://api.nium.com")
NIUM_CLIENT_HASH = os.environ.get("NIUM_CLIENT_HASH_ID", "")


# ═══════════════════════════════════════════════
# Multi-Strategy Authentication Engine
# ═══════════════════════════════════════════════

BASE_URLS = [
    "https://api.nium.com",
    "https://sandbox.nium.com",
    "https://gateway.nium.com",
]

class AuthStrategy:
    """Represents a single authentication approach."""
    def __init__(self, name: str, base_url: str, auth_type: str, token: str = ""):
        self.name = name
        self.base_url = base_url
        self.auth_type = auth_type  # "x-api-key" or "bearer"
        self.token = token
        self.working = None  # None=untested, True=works, False=failed
        self.last_tested = None
        self.error = ""

    def headers(self) -> dict:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-request-id": str(uuid.uuid4()),
            "x-client-name": "NeoNobleRamp",
        }
        if self.auth_type == "x-api-key":
            h["x-api-key"] = NIUM_API_KEY
        elif self.auth_type == "bearer":
            h["Authorization"] = f"Bearer {self.token or NIUM_API_KEY}"
        return h

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "auth_type": self.auth_type,
            "working": self.working,
            "last_tested": self.last_tested,
            "error": self.error[:200] if self.error else "",
        }


class NiumAuthDiscovery:
    """
    Automatically discovers which NIUM auth strategy works.
    Tries all combinations and caches the working one.
    """

    def __init__(self):
        self._strategies: List[AuthStrategy] = []
        self._active: Optional[AuthStrategy] = None
        self._bearer_tokens: dict = {}  # base_url -> (token, expiry)
        self._discovery_in_progress = False
        self._last_discovery = None
        self._build_strategies()

    def _build_strategies(self):
        """Build all possible auth strategies."""
        self._strategies = []
        for url in BASE_URLS:
            self._strategies.append(AuthStrategy(
                f"x-api-key@{url.split('//')[1]}",
                url, "x-api-key"
            ))
            self._strategies.append(AuthStrategy(
                f"bearer@{url.split('//')[1]}",
                url, "bearer"
            ))

    async def _get_bearer_token(self, base_url: str) -> Optional[str]:
        """Authenticate via /client/auth to get Bearer token."""
        cached = self._bearer_tokens.get(base_url)
        if cached and cached[1] > datetime.now(timezone.utc):
            return cached[0]

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{base_url}/api/v1/client/auth",
                    json={"apiKey": NIUM_API_KEY, "password": NIUM_API_KEY, "type": "CLIENT_API"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    token = data.get("token", "")
                    if token:
                        self._bearer_tokens[base_url] = (token, datetime.now(timezone.utc) + timedelta(minutes=14))
                        logger.info(f"[NIUM] Bearer token obtained from {base_url}")
                        return token
        except Exception as e:
            logger.debug(f"[NIUM] Bearer auth failed on {base_url}: {e}")
        return None

    async def _test_strategy(self, strategy: AuthStrategy) -> bool:
        """Test if a strategy works by calling a lightweight endpoint."""
        try:
            if strategy.auth_type == "bearer":
                token = await self._get_bearer_token(strategy.base_url)
                if not token:
                    strategy.working = False
                    strategy.error = "Bearer token acquisition failed"
                    strategy.last_tested = datetime.now(timezone.utc).isoformat()
                    return False
                strategy.token = token

            headers = strategy.headers()
            # Test with a lightweight endpoint — get client info
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{strategy.base_url}/api/v1/client/{NIUM_CLIENT_HASH}",
                    headers=headers,
                )
                strategy.last_tested = datetime.now(timezone.utc).isoformat()
                if resp.status_code in (200, 201):
                    strategy.working = True
                    strategy.error = ""
                    logger.info(f"[NIUM] Strategy WORKS: {strategy.name}")
                    return True
                else:
                    strategy.working = False
                    strategy.error = resp.text[:200]
                    logger.debug(f"[NIUM] Strategy failed: {strategy.name} → {resp.status_code}")
                    return False
        except Exception as e:
            strategy.working = False
            strategy.error = str(e)[:200]
            strategy.last_tested = datetime.now(timezone.utc).isoformat()
            return False

    async def discover(self, force: bool = False) -> Optional[AuthStrategy]:
        """
        Try all strategies and return the first working one.
        Results are cached for 30 minutes unless forced.
        """
        if self._active and self._active.working and not force:
            if self._last_discovery and (datetime.now(timezone.utc) - self._last_discovery) < timedelta(minutes=30):
                return self._active

        if self._discovery_in_progress:
            # Wait for existing discovery
            for _ in range(30):
                await asyncio.sleep(1)
                if not self._discovery_in_progress:
                    return self._active
            return self._active

        self._discovery_in_progress = True
        db = get_database()

        try:
            logger.info("[NIUM] Starting auth discovery across all strategies...")
            discovery_log = {
                "id": str(uuid.uuid4()),
                "type": "auth_discovery",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "strategies_tested": [],
            }

            for strategy in self._strategies:
                result = await self._test_strategy(strategy)
                discovery_log["strategies_tested"].append(strategy.to_dict())

                if result:
                    self._active = strategy
                    self._last_discovery = datetime.now(timezone.utc)
                    discovery_log["result"] = f"SUCCESS: {strategy.name}"
                    discovery_log["completed_at"] = datetime.now(timezone.utc).isoformat()
                    await db.nium_api_logs.insert_one({**discovery_log, "_id": discovery_log["id"]})
                    return strategy

            # None worked
            self._active = None
            self._last_discovery = datetime.now(timezone.utc)
            discovery_log["result"] = "FAILED: No working strategy found"
            discovery_log["completed_at"] = datetime.now(timezone.utc).isoformat()
            await db.nium_api_logs.insert_one({**discovery_log, "_id": discovery_log["id"]})
            return None

        finally:
            self._discovery_in_progress = False

    async def execute(self, method: str, path: str, json_data: dict = None) -> dict:
        """
        Execute authenticated request using the discovered strategy.
        For customer creation, auto-tries v3, v4, v2, v1 endpoints.
        Adapts address payload format per API version.
        """
        strategy = await self.discover()

        if not strategy:
            return {
                "error": True, "status_code": 503,
                "detail": "Nessuna strategia NIUM funzionante.",
                "strategies_tested": [s.to_dict() for s in self._strategies],
            }

        db = get_database()
        is_customer_create = method == "POST" and "/customer" in path and path.count("/") <= 5
        versions = ["v2", "v3", "v4", "v1"] if is_customer_create else [None]

        best_result = None
        for version in versions:
            if version:
                versioned_path = path
                for v in ["v1", "v2", "v3", "v4"]:
                    versioned_path = versioned_path.replace(f"/api/{v}/", f"/api/{version}/")
                url = f"{strategy.base_url}{versioned_path}"
                # Adapt payload format for each version
                payload = self._adapt_payload(json_data, version) if json_data else None
            else:
                url = f"{strategy.base_url}{path}"
                payload = json_data

            headers = strategy.headers()
            request_id = headers.get("x-request-id", str(uuid.uuid4()))

            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    if method == "POST":
                        resp = await client.post(url, json=payload, headers=headers)
                    elif method == "PUT":
                        resp = await client.put(url, json=payload, headers=headers)
                    elif method == "GET":
                        resp = await client.get(url, headers=headers)
                    else:
                        resp = await client.request(method, url, json=payload, headers=headers)

                    await db.nium_api_logs.insert_one({
                        "_id": request_id,
                        "strategy": strategy.name,
                        "method": method, "url": url,
                        "status_code": resp.status_code, "version": version,
                        "response_preview": resp.text[:500],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })

                    logger.info(f"[NIUM] {version or 'default'} {method} {url} → {resp.status_code}")

                    if resp.status_code in (200, 201):
                        result = resp.json() if resp.text else {"success": True}
                        result["_nium_version_used"] = version or "default"
                        return result

                    result = {
                        "error": True, "status_code": resp.status_code,
                        "detail": resp.text[:500], "strategy_used": strategy.name,
                        "version_used": version or "default", "request_id": request_id,
                    }

                    # Auth failures: try next version
                    if resp.status_code in (401, 403) and "Missing Authentication" in resp.text:
                        continue

                    # 404 (templateId missing etc.): try next version
                    if resp.status_code == 404:
                        best_result = best_result or result
                        continue

                    # Validation errors: keep best result but try next version
                    if resp.status_code == 400:
                        best_result = best_result or result
                        continue

                    # Other errors: return immediately
                    return result

            except Exception as e:
                logger.error(f"[NIUM] Request error ({version}): {e}")
                best_result = best_result or {"error": True, "detail": str(e)}

        return best_result or {"error": True, "detail": "Tutte le versioni API fallite"}

    @staticmethod
    def _adapt_payload(data: dict, version: str) -> dict:
        """Adapt payload fields for specific API version."""
        if not data:
            return data
        payload = dict(data)

        # v2 uses both flat billing and nested address
        if version == "v2":
            addr = {}
            for src, dst in [
                ("billingAddress1", "addressLine1"),
                ("billingCity", "city"),
                ("billingState", "state"),
                ("billingZipCode", "postcode"),
                ("billingCountry", "country"),
            ]:
                if src in payload:
                    addr[dst] = payload[src]
            if addr:
                payload["address"] = addr

        return payload

    def get_status(self) -> dict:
        return {
            "active_strategy": self._active.to_dict() if self._active else None,
            "all_strategies": [s.to_dict() for s in self._strategies],
            "last_discovery": self._last_discovery.isoformat() if self._last_discovery else None,
            "discovery_in_progress": self._discovery_in_progress,
        }


# Global instance
_auth = NiumAuthDiscovery()


# ═══════════════════════════════════════════════
# Models
# ═══════════════════════════════════════════════

class IdentificationDoc(BaseModel):
    identification_type: str
    identification_value: str
    identification_doc_expiry: Optional[str] = None

class TaxDetail(BaseModel):
    country_of_residence: str
    tax_id_number: str

class OnboardCustomerRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    country_code: str = Field(default="IT")
    nationality: str = Field(default="IT")
    date_of_birth: str = Field(description="YYYY-MM-DD")
    mobile: str
    kyc_mode: str = Field(default="E_KYC")
    billing_address1: str = Field(default="")
    billing_city: str = Field(default="")
    billing_zip_code: str = Field(default="")
    billing_country: str = Field(default="IT")
    billing_state: Optional[str] = None
    country_of_birth: Optional[str] = None
    pep: bool = False
    verification_consent: bool = True
    intended_use_of_account: str = Field(default="Day-to-day spending")
    estimated_monthly_funding: str = Field(default="1000-5000")
    identification_doc: Optional[List[IdentificationDoc]] = None
    tax_details: Optional[List[TaxDetail]] = None

class UpdateCustomerRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None
    billing_address1: Optional[str] = None
    billing_city: Optional[str] = None
    billing_zip_code: Optional[str] = None

class UploadDocumentRequest(BaseModel):
    document_type: str
    document_front_base64: str
    document_back_base64: Optional[str] = None

class RfiResponseRequest(BaseModel):
    rfi_hash_id: str
    rfi_response_fields: dict


# ═══════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════

@router.post("/create-customer")
async def create_nium_customer(
    req: OnboardCustomerRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create NIUM customer with auto-discovered authentication."""
    if not NIUM_API_KEY or not NIUM_CLIENT_HASH:
        raise HTTPException(status_code=503, detail="NIUM_API_KEY o NIUM_CLIENT_HASH_ID mancante nel .env")

    db = get_database()
    uid = current_user["user_id"]

    user = await db.users.find_one({"id": uid}, {"_id": 0})
    if user and user.get("nium_customer_hash") and user.get("nium_mode") == "live":
        return {
            "message": "Cliente NIUM gia presente",
            "customer_hash": user["nium_customer_hash"],
            "wallet_hash": user.get("nium_wallet_hash", ""),
            "status": "existing",
        }

    valid_modes = ["E_KYC", "MANUAL_KYC", "E_DOC_VERIFY", "SCREENING_KYC"]
    if req.kyc_mode.upper() not in valid_modes:
        raise HTTPException(status_code=400, detail=f"kycMode non valido. Supportati: {', '.join(valid_modes)}")

    # Map user-friendly strings to NIUM enum codes
    MONTHLY_FUNDING_MAP = {
        "0-1000": "MF001", "1000-5000": "MF002", "5000-10000": "MF003",
        "10000-50000": "MF004", "50000+": "MF005",
    }
    USE_OF_ACCOUNT_MAP = {
        "Day-to-day spending": "IU100", "Savings": "IU200",
        "International transfers": "IU300", "Business payments": "IU400",
    }

    emf = MONTHLY_FUNDING_MAP.get(req.estimated_monthly_funding, req.estimated_monthly_funding)
    iua = USE_OF_ACCOUNT_MAP.get(req.intended_use_of_account, req.intended_use_of_account)

    payload = {
        "firstName": req.first_name,
        "lastName": req.last_name,
        "email": req.email,
        "nationality": req.nationality,
        "countryCode": req.country_code,
        "mobile": int(req.mobile.replace("+", "").replace(" ", "")) if req.mobile else 0,
        "dateOfBirth": req.date_of_birth,
        "kycMode": req.kyc_mode.upper(),
        "estimatedMonthlyFunding": emf,
        "intendedUseOfAccount": iua,
        "verificationConsent": True,
        "pep": req.pep,
        "region": req.country_code or "EU",
    }

    # Add templateId if configured in env
    template_id = os.environ.get("NIUM_TEMPLATE_ID", "")
    if template_id:
        payload["templateId"] = template_id

    if req.billing_address1:
        payload["billingAddress1"] = req.billing_address1
    if req.billing_city:
        payload["billingCity"] = req.billing_city
    if req.billing_zip_code:
        payload["billingZipCode"] = req.billing_zip_code
    if req.billing_country:
        payload["billingCountry"] = req.billing_country
    if req.billing_state:
        payload["billingState"] = req.billing_state
    if req.country_of_birth:
        payload["countryOfBirth"] = req.country_of_birth
    if req.identification_doc:
        payload["identificationDoc"] = [
            {"identificationType": d.identification_type, "identificationValue": d.identification_value,
             **({"identificationDocExpiry": d.identification_doc_expiry} if d.identification_doc_expiry else {})}
            for d in req.identification_doc
        ]
    if req.tax_details:
        payload["taxDetails"] = [
            {"countryOfResidence": t.country_of_residence, "taxIdNumber": t.tax_id_number}
            for t in req.tax_details
        ]

    # Multi-version customer creation: try v2 first (Unified API), then v3, v4, v1
    result = None
    versions_tried = []
    for ver in ["v2", "v3", "v4", "v1"]:
        endpoint = f"/api/{ver}/client/{NIUM_CLIENT_HASH}/customer"
        result = await _auth.execute("POST", endpoint, payload)
        versions_tried.append(ver)
        if not result.get("error"):
            break
        # If template-specific error, no point retrying other versions with same config
        err_detail = str(result.get("detail", ""))
        if "templateId" in err_detail or "Configuration not found" in err_detail:
            logger.warning(f"[NIUM] Template config issue on {ver}: {err_detail[:100]}")
            continue
        if result.get("status_code") in (400, 403):
            logger.warning(f"[NIUM] {ver} returned {result.get('status_code')}: {err_detail[:100]}")
            continue

    if result.get("error"):
        error_detail = result.get("detail", "")
        troubleshooting = []
        if "templateId" in error_detail or "Configuration not found" in error_detail:
            troubleshooting = [
                "L'account NIUM necessita di un template di onboarding configurato.",
                "Accedi al portale NIUM Admin (https://admin.nium.com) > Configurazione > Templates",
                "Usa la Fetch Corporate Constants API per ottenere i templateId validi",
                f"Versioni API provate automaticamente: {', '.join(versions_tried)}",
                "Imposta NIUM_TEMPLATE_ID nel .env del backend dopo aver configurato il template",
                f"Client Hash ID: {NIUM_CLIENT_HASH}",
                "Autenticazione API funzionante: x-api-key su gateway.nium.com",
            ]
        elif "Forbidden" in error_detail:
            troubleshooting = [
                "L'API key non ha i permessi per la creazione clienti",
                f"Versioni API provate: {', '.join(versions_tried)}",
            ]

        raise HTTPException(
            status_code=result.get("status_code", 502),
            detail={
                "message": "Errore NIUM API",
                "nium_error": error_detail,
                "strategy_used": result.get("strategy_used", ""),
                "versions_tried": versions_tried,
                "auto_discovery": f"Provate {len(versions_tried)} versioni API su gateway.nium.com",
                "troubleshooting": troubleshooting,
            },
        )

    customer_hash = result.get("customerHashId", "")
    wallet_hash = result.get("walletHashId", "")

    await db.users.update_one(
        {"id": uid},
        {"$set": {
            "nium_customer_hash": customer_hash,
            "nium_wallet_hash": wallet_hash,
            "nium_onboarded_at": datetime.now(timezone.utc).isoformat(),
            "nium_mode": "live",
            "nium_kyc_mode": req.kyc_mode.upper(),
            "nium_compliance_status": result.get("complianceStatus", "INITIATED"),
        }},
    )
    return {
        "message": "Cliente NIUM creato con successo",
        "customer_hash": customer_hash,
        "wallet_hash": wallet_hash,
        "compliance_status": result.get("complianceStatus", "INITIATED"),
        "status": "live",
    }


@router.get("/status")
async def get_onboarding_status(current_user: dict = Depends(get_current_user)):
    db = get_database()
    user = await db.users.find_one(
        {"id": current_user["user_id"]},
        {"_id": 0, "nium_customer_hash": 1, "nium_wallet_hash": 1,
         "nium_mode": 1, "nium_onboarded_at": 1, "nium_kyc_mode": 1,
         "nium_compliance_status": 1},
    )
    if not user or not user.get("nium_customer_hash"):
        return {"onboarded": False, "nium_configured": bool(NIUM_API_KEY and NIUM_CLIENT_HASH)}
    return {
        "onboarded": True,
        "customer_hash": user["nium_customer_hash"],
        "wallet_hash": user.get("nium_wallet_hash", ""),
        "mode": user.get("nium_mode", ""),
        "kyc_mode": user.get("nium_kyc_mode", ""),
        "compliance_status": user.get("nium_compliance_status", ""),
        "onboarded_at": user.get("nium_onboarded_at"),
    }


@router.get("/customer-details")
async def get_customer_details(current_user: dict = Depends(get_current_user)):
    db = get_database()
    user = await db.users.find_one({"id": current_user["user_id"]}, {"_id": 0})
    if not user or not user.get("nium_customer_hash"):
        raise HTTPException(status_code=404, detail="Cliente NIUM non trovato")
    result = await _auth.execute("GET", f"/api/v1/client/{NIUM_CLIENT_HASH}/customer/{user['nium_customer_hash']}")
    if result.get("error"):
        raise HTTPException(status_code=result.get("status_code", 502), detail=result.get("detail", ""))
    return {"customer": result, "source": "nium_live"}


@router.get("/compliance-status")
async def get_compliance_status(current_user: dict = Depends(get_current_user)):
    db = get_database()
    user = await db.users.find_one({"id": current_user["user_id"]}, {"_id": 0})
    if not user or not user.get("nium_customer_hash"):
        raise HTTPException(status_code=404, detail="Cliente NIUM non trovato")
    result = await _auth.execute("GET", f"/api/v1/client/{NIUM_CLIENT_HASH}/customer/{user['nium_customer_hash']}")
    if result.get("error"):
        raise HTTPException(status_code=result.get("status_code", 502), detail=result.get("detail", ""))
    compliance = result.get("complianceStatus", "UNKNOWN")
    await db.users.update_one({"id": current_user["user_id"]}, {"$set": {"nium_compliance_status": compliance}})
    return {
        "compliance_status": compliance,
        "kyc_status": result.get("kycStatus", ""),
        "customer_hash": user["nium_customer_hash"],
    }


@router.post("/upload-document")
async def upload_document(req: UploadDocumentRequest, current_user: dict = Depends(get_current_user)):
    db = get_database()
    user = await db.users.find_one({"id": current_user["user_id"]}, {"_id": 0})
    if not user or not user.get("nium_customer_hash"):
        raise HTTPException(status_code=404, detail="Cliente NIUM non trovato")
    payload = {"documentType": req.document_type, "document": req.document_front_base64}
    if req.document_back_base64:
        payload["documentBack"] = req.document_back_base64
    result = await _auth.execute("POST", f"/api/v1/client/{NIUM_CLIENT_HASH}/customer/{user['nium_customer_hash']}/documents", payload)
    if result.get("error"):
        raise HTTPException(status_code=result.get("status_code", 502), detail=result.get("detail", ""))
    return {"message": "Documento caricato su NIUM", "result": result}


@router.post("/respond-rfi")
async def respond_to_rfi(req: RfiResponseRequest, current_user: dict = Depends(get_current_user)):
    db = get_database()
    user = await db.users.find_one({"id": current_user["user_id"]}, {"_id": 0})
    if not user or not user.get("nium_customer_hash"):
        raise HTTPException(status_code=404, detail="Cliente NIUM non trovato")
    result = await _auth.execute("POST", f"/api/v1/client/{NIUM_CLIENT_HASH}/customer/{user['nium_customer_hash']}/rfi/{req.rfi_hash_id}", req.rfi_response_fields)
    if result.get("error"):
        raise HTTPException(status_code=result.get("status_code", 502), detail=result.get("detail", ""))
    return {"message": "Risposta RFI inviata", "result": result}


@router.post("/update-customer")
async def update_customer(req: UpdateCustomerRequest, current_user: dict = Depends(get_current_user)):
    db = get_database()
    user = await db.users.find_one({"id": current_user["user_id"]}, {"_id": 0})
    if not user or not user.get("nium_customer_hash"):
        raise HTTPException(status_code=404, detail="Cliente NIUM non trovato")
    payload = {}
    for field, nium_key in [("first_name","firstName"),("last_name","lastName"),("email","email"),("mobile","mobile"),("billing_address1","billingAddress1"),("billing_city","billingCity"),("billing_zip_code","billingZipCode")]:
        val = getattr(req, field, None)
        if val:
            payload[nium_key] = val
    if not payload:
        raise HTTPException(status_code=400, detail="Nessun campo da aggiornare")
    result = await _auth.execute("PUT", f"/api/v1/client/{NIUM_CLIENT_HASH}/customer/{user['nium_customer_hash']}", payload)
    if result.get("error"):
        raise HTTPException(status_code=result.get("status_code", 502), detail=result.get("detail", ""))
    return {"message": "Dati cliente aggiornati", "result": result}


@router.get("/available-methods")
async def get_available_methods():
    return {
        "nium_configured": bool(NIUM_API_KEY and NIUM_CLIENT_HASH),
        "nium_base_url": NIUM_BASE_URL,
        "client_hash_id": NIUM_CLIENT_HASH,
        "auto_discovery": "enabled",
        "available_kyc_modes": [
            {"mode": "E_KYC", "description": "Verifica elettronica automatica"},
            {"mode": "MANUAL_KYC", "description": "Upload manuale documenti + revisione"},
            {"mode": "E_DOC_VERIFY", "description": "Verifica elettronica documenti"},
            {"mode": "SCREENING_KYC", "description": "Solo screening compliance base"},
        ],
    }


class SetTemplateRequest(BaseModel):
    template_id: str


@router.post("/set-template-id")
async def set_nium_template_id(req: SetTemplateRequest, current_user: dict = Depends(get_current_user)):
    """Admin: Set NIUM_TEMPLATE_ID at runtime (persisted in DB config)."""
    db = get_database()
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Solo admin possono configurare il template NIUM")

    os.environ["NIUM_TEMPLATE_ID"] = req.template_id

    await db.platform_config.update_one(
        {"key": "NIUM_TEMPLATE_ID"},
        {"$set": {"key": "NIUM_TEMPLATE_ID", "value": req.template_id, "updated_by": current_user["user_id"]}},
        upsert=True,
    )
    return {"message": f"NIUM_TEMPLATE_ID impostato: {req.template_id}", "active": True}



@router.get("/auth-discovery-status")
async def auth_discovery_status():
    """Show current NIUM auth discovery status and all tested strategies."""
    return _auth.get_status()


@router.post("/auth-discovery-reset")
async def auth_discovery_reset():
    """Force re-discovery of NIUM authentication strategy."""
    result = await _auth.discover(force=True)
    return {
        "message": "Discovery completata" if result else "Nessuna strategia funzionante trovata",
        "active": result.to_dict() if result else None,
        "all_strategies": [s.to_dict() for s in _auth._strategies],
    }


@router.get("/templates")
async def list_nium_templates():
    """Attempt to fetch available onboarding templates from NIUM."""
    if not NIUM_API_KEY or not NIUM_CLIENT_HASH:
        raise HTTPException(status_code=503, detail="NIUM non configurato")

    result = await _auth.execute("GET", f"/api/v1/client/{NIUM_CLIENT_HASH}/templates")

    template_id_env = os.environ.get("NIUM_TEMPLATE_ID", "")
    return {
        "nium_response": result if not result.get("error") else None,
        "error": result.get("detail") if result.get("error") else None,
        "configured_template_id": template_id_env or None,
        "hint": "Se il template non e' configurato, accedi al portale NIUM Admin > Templates > Crea template individuale. Poi imposta NIUM_TEMPLATE_ID nel .env",
    }


@router.get("/diagnostic")
async def nium_diagnostic():
    """Full NIUM integration diagnostic — checks auth, client info, and configuration status."""
    diag = {
        "api_key_set": bool(NIUM_API_KEY),
        "client_hash_set": bool(NIUM_CLIENT_HASH),
        "template_id_set": bool(os.environ.get("NIUM_TEMPLATE_ID")),
        "auth_strategy": None,
        "client_info": None,
        "template_info": None,
        "recommendations": [],
    }

    strategy = await _auth.discover()
    if strategy:
        diag["auth_strategy"] = strategy.to_dict()
    else:
        diag["recommendations"].append("Nessuna strategia NIUM funzionante. Verificare API key e Client Hash.")
        return diag

    # Try to get client info
    client_result = await _auth.execute("GET", f"/api/v1/client/{NIUM_CLIENT_HASH}")
    if not client_result.get("error"):
        diag["client_info"] = {
            "name": client_result.get("name", ""),
            "status": client_result.get("status", ""),
            "country": client_result.get("countryCode", ""),
        }
    else:
        diag["recommendations"].append(f"Client info non disponibile: {client_result.get('detail', '')[:100]}")

    # Check template
    if not os.environ.get("NIUM_TEMPLATE_ID"):
        diag["recommendations"].append("NIUM_TEMPLATE_ID non configurato. Impostarlo in .env se la creazione clienti fallisce con 404.")

    return diag


@router.get("/corporate-constants")
async def fetch_corporate_constants():
    """Fetch NIUM corporate constants including available template IDs and configuration options."""
    if not NIUM_API_KEY or not NIUM_CLIENT_HASH:
        raise HTTPException(status_code=503, detail="NIUM non configurato")

    results = {}

    # Try fetching corporate constants from multiple endpoints
    for endpoint_name, path in [
        ("constants", f"/api/v1/client/{NIUM_CLIENT_HASH}/corporateConstants"),
        ("settings", f"/api/v1/client/{NIUM_CLIENT_HASH}/settings"),
        ("programs", f"/api/v1/client/{NIUM_CLIENT_HASH}/programs"),
    ]:
        result = await _auth.execute("GET", path)
        if not result.get("error"):
            results[endpoint_name] = result
        else:
            results[endpoint_name] = {"error": result.get("detail", "")[:200]}

    return {
        "client_hash": NIUM_CLIENT_HASH,
        "data": results,
        "configured_template_id": os.environ.get("NIUM_TEMPLATE_ID", None),
        "hint": "Usa i templateId ritornati qui per impostare NIUM_TEMPLATE_ID nel .env",
    }

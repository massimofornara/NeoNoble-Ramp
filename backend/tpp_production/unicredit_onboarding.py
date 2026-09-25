"""UniCredit TPP onboarding request builder.

The QWAC is issued by an EU Trusted List QTSP and must already exist.
This module never generates or stores a private key and never treats a
self-signed certificate as a production credential.
"""
from __future__ import annotations
import base64, hashlib, uuid
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class OnboardingRequest:
    user_email: str
    payload: dict[str, Any]

def new_request_id() -> str:
    return str(uuid.uuid4())

def digest_body(body: bytes) -> str:
    return "SHA-256=" + base64.b64encode(hashlib.sha256(body).digest()).decode()

def build_headers(body: bytes, signature: str | None = None,
                  signing_certificate_b64: str | None = None) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "X-Request-ID": new_request_id(),
        "Digest": digest_body(body),
    }
    if signature:
        headers["Signature"] = signature
    if signing_certificate_b64:
        headers["TPP-Signature-Certificate"] = signing_certificate_b64
    return headers

def production_preflight(qwac_present: bool, regulatory_authorized: bool,
                         pisp_enabled: bool, aisp_enabled: bool) -> None:
    missing = []
    if not qwac_present: missing.append("QWAC")
    if not regulatory_authorized: missing.append("regulatory_authorization")
    if not (pisp_enabled or aisp_enabled): missing.append("TPP_role")
    if missing:
        raise RuntimeError("UNICREDIT_PRODUCTION_PREREQUISITES_MISSING:" + ",".join(missing))

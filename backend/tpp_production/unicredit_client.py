"""UniCredit PSD2 transport layer for NeoNoble.

The module deliberately contains no credentials or private keys. It supports
mTLS using paths supplied through environment variables and provides the
transport primitives required by the UniCredit TPP onboarding/API layer.
"""
from __future__ import annotations

import base64
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import httpx

from .config import TPPConfig


class UniCreditClient:
    def __init__(self, config: TPPConfig | None = None) -> None:
        self.config = config or TPPConfig()

    def _request_id(self) -> str:
        return str(uuid.uuid4())

    def _mtls(self) -> tuple[str, str] | None:
        if not (self.config.qwac_cert_path and self.config.qwac_key_path):
            return None
        if not Path(self.config.qwac_cert_path).is_file():
            raise RuntimeError("Configured QWAC certificate file does not exist")
        if not Path(self.config.qwac_key_path).is_file():
            raise RuntimeError("Configured QWAC private key file does not exist")
        return self.config.qwac_cert_path, self.config.qwac_key_path

    @staticmethod
    def digest_json(payload: dict[str, Any]) -> str:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        return "SHA-256=" + base64.b64encode(hashlib.sha256(body).digest()).decode()

    async def onboarding(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": self._request_id(),
        }
        digest = self.digest_json(payload)
        headers["Digest"] = digest

        async with httpx.AsyncClient(cert=self._mtls(), timeout=30.0) as client:
            response = await client.post(
                f"{self.config.api_base_url}/tpp/v1/authentications",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Request-ID": self._request_id(),
            **(headers or {}),
        }
        async with httpx.AsyncClient(cert=self._mtls(), timeout=30.0) as client:
            return await client.request(
                method,
                f"{self.config.api_base_url.rstrip('/')}/{path.lstrip('/')}",
                headers=request_headers,
                json=json_body,
            )

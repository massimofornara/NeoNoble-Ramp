"""
Circle USDC Programmable Wallets Service — NeoNoble Ramp.

Real Circle API integration for institutional USDC settlement.
Manages 3 segregated wallets:
  - CLIENT: receives incoming deposits
  - TREASURY: operational funds for execution
  - REVENUE: fee/profit collection

NO SIMULATION. Only real API calls and on-chain verified balances.
"""

import os
import uuid
import logging
import httpx
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal
from web3 import Web3

from database.mongodb import get_database

logger = logging.getLogger("circle_wallet")

# USDC contract addresses per chain
USDC_CONTRACTS = {
    "ETH": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "POLYGON": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
    "BSC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    "ARB": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
}

USDC_DECIMALS = {
    "ETH": 6,
    "POLYGON": 6,
    "BSC": 18,
    "ARB": 6,
}

ERC20_BALANCE_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


class WalletRole:
    CLIENT = "client"
    TREASURY = "treasury"
    REVENUE = "revenue"


# Segregated wallet addresses (user-provided)
SEGREGATED_WALLETS = {
    WalletRole.CLIENT: "0xf44C81dbab89941173d0d49C1CEA876950eDCfd3",
    WalletRole.TREASURY: "0x837799C8B457B21ab54Be374092BEEBa6EA47587",
    WalletRole.REVENUE: "0xF7ba3C8E9F667E864edcD2F0A4579F1E8274fD44",
}


class CircleWalletService:
    """Real Circle USDC API integration with on-chain balance verification."""

    _instance = None

    def __init__(self):
        self._api_key = None
        self._base_url = "https://api.circle.com"
        self._client: Optional[httpx.AsyncClient] = None
        self._initialized = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self):
        """Initialize Circle API client with credentials from .env."""
        self._api_key = os.environ.get("CIRCLE_API_KEY", "")
        env = os.environ.get("CIRCLE_ENVIRONMENT", "production")

        if env == "sandbox":
            self._base_url = "https://api.sandbox.circle.com"
        else:
            self._base_url = "https://api.circle.com"

        if not self._api_key:
            logger.warning("[CIRCLE] CIRCLE_API_KEY not set — Circle USDC rail disabled")
            return

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )
        self._initialized = True
        logger.info(f"[CIRCLE] Service initialized — base={self._base_url}, wallets={len(SEGREGATED_WALLETS)}")

    @property
    def is_active(self) -> bool:
        return self._initialized and self._client is not None

    # ─────────────────────────────────────────────
    #  ON-CHAIN USDC BALANCE (Real RPC verification)
    # ─────────────────────────────────────────────

    def _get_web3(self, chain: str = "BSC") -> Optional[Web3]:
        """Get Web3 connection for on-chain USDC balance checks."""
        rpc_map = {
            "BSC": os.environ.get("BSC_RPC_URL", "https://bsc-dataseed1.binance.org"),
            "ETH": "https://eth-mainnet.g.alchemy.com/v2/demo",
            "POLYGON": "https://polygon-rpc.com",
        }
        rpc = rpc_map.get(chain)
        if not rpc:
            return None
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 10}))
            if w3.is_connected():
                return w3
        except Exception:
            pass
        return None

    async def get_onchain_usdc_balance(self, address: str, chain: str = "BSC") -> dict:
        """Get REAL on-chain USDC balance for any address."""
        w3 = self._get_web3(chain)
        if not w3:
            return {"balance": 0, "verified": False, "error": f"No RPC for {chain}"}

        contract_addr = USDC_CONTRACTS.get(chain)
        if not contract_addr:
            return {"balance": 0, "verified": False, "error": f"No USDC contract for {chain}"}

        try:
            # Normalize address: pad to 42 chars if truncated
            normalized = address.lower().strip()
            if normalized.startswith("0x") and len(normalized) < 42:
                normalized = "0x" + normalized[2:].zfill(40)
            checksum_addr = Web3.to_checksum_address(normalized)
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(contract_addr),
                abi=ERC20_BALANCE_ABI,
            )
            raw = contract.functions.balanceOf(checksum_addr).call()
            decimals = USDC_DECIMALS.get(chain, 6)
            balance = float(Decimal(raw) / Decimal(10**decimals))
            return {
                "balance": round(balance, 6),
                "raw": raw,
                "contract": contract_addr,
                "chain": chain,
                "verified": True,
                "block": w3.eth.block_number,
            }
        except Exception as e:
            logger.error(f"[CIRCLE] On-chain USDC balance error for {address}: {e}")
            return {"balance": 0, "verified": False, "error": str(e)}

    # ─────────────────────────────────────────────
    #  SEGREGATED WALLET BALANCES
    # ─────────────────────────────────────────────

    async def get_all_wallet_balances(self, chain: str = "BSC") -> dict:
        """Get real USDC balances for all 3 segregated wallets."""
        results = {}
        for role, address in SEGREGATED_WALLETS.items():
            bal = await self.get_onchain_usdc_balance(address, chain)
            results[role] = {
                "address": address,
                "role": role,
                **bal,
            }

        total = sum(r["balance"] for r in results.values() if r.get("verified"))
        return {
            "wallets": results,
            "total_usdc": round(total, 6),
            "chain": chain,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    # ─────────────────────────────────────────────
    #  CIRCLE API: Wallet Operations
    # ─────────────────────────────────────────────

    async def _api_call(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Make authenticated Circle API call."""
        if not self._client:
            return {"error": "Circle client not initialized", "success": False}
        try:
            if method == "GET":
                resp = await self._client.get(endpoint)
            elif method == "POST":
                resp = await self._client.post(endpoint, json=data)
            else:
                return {"error": f"Unsupported method: {method}", "success": False}

            result = resp.json()
            if resp.status_code >= 400:
                logger.warning(f"[CIRCLE] API {method} {endpoint} → {resp.status_code}: {result}")
                return {"error": result, "status_code": resp.status_code, "success": False}

            return {"data": result, "status_code": resp.status_code, "success": True}
        except Exception as e:
            logger.error(f"[CIRCLE] API error: {e}")
            return {"error": str(e), "success": False}

    async def create_wallet(self) -> dict:
        """Create a new Circle programmable wallet."""
        idempotency_key = str(uuid.uuid4())
        return await self._api_call("POST", "/v1/wallets", {"idempotencyKey": idempotency_key})

    async def get_wallet_info(self, wallet_id: str) -> dict:
        """Get Circle wallet details and balances."""
        return await self._api_call("GET", f"/v1/wallets/{wallet_id}")

    async def transfer_usdc(
        self,
        from_wallet_id: str,
        to_address: str,
        amount: str,
    ) -> dict:
        """Transfer USDC via Circle API."""
        idempotency_key = str(uuid.uuid4())
        data = {
            "idempotencyKey": idempotency_key,
            "destination": {
                "type": "blockchain",
                "address": to_address,
            },
            "amounts": [{"amount": amount, "currency": "USD"}],
        }
        return await self._api_call("POST", f"/v1/wallets/{from_wallet_id}/transfers", data)

    async def get_transfer_status(self, wallet_id: str, transfer_id: str) -> dict:
        """Query Circle transfer status."""
        return await self._api_call("GET", f"/v1/wallets/{wallet_id}/transfers/{transfer_id}")

    async def list_transfers(self, wallet_id: str) -> dict:
        """List all transfers for a Circle wallet."""
        return await self._api_call("GET", f"/v1/wallets/{wallet_id}/transfers")

    # ─────────────────────────────────────────────
    #  AUDIT LOGGING
    # ─────────────────────────────────────────────

    async def log_operation(self, op_type: str, details: dict):
        """Log every Circle operation to audit trail."""
        db = get_database()
        await db.circle_audit_log.insert_one({
            "id": str(uuid.uuid4()),
            "operation": op_type,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ─────────────────────────────────────────────
    #  HEALTH / DIAGNOSTIC
    # ─────────────────────────────────────────────

    async def get_diagnostic(self) -> dict:
        """Full Circle integration health check."""
        api_status = "not_configured"
        api_test = None

        if self._client:
            # Test API connectivity
            try:
                resp = await self._client.get("/ping")
                api_status = "connected" if resp.status_code < 500 else "error"
                api_test = {"status_code": resp.status_code}
            except Exception as e:
                api_status = "unreachable"
                api_test = {"error": str(e)}

        # On-chain balances
        balances = await self.get_all_wallet_balances("BSC")

        return {
            "service": "Circle USDC Programmable Wallets",
            "api_status": api_status,
            "api_test": api_test,
            "environment": os.environ.get("CIRCLE_ENVIRONMENT", "production"),
            "segregated_wallets": SEGREGATED_WALLETS,
            "onchain_balances": balances,
            "rules": {
                "client_wallet": "Receives ALL incoming USDC deposits",
                "treasury_wallet": "Operational funds for trade execution",
                "revenue_wallet": "Fee and profit collection ONLY",
            },
        }

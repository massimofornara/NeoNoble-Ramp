"""
DEX Swap Service — NeoNoble Ramp.

Real on-chain DEX swaps via PancakeSwap V2 (BSC Mainnet):
- NENO → WBNB → USDC (2-hop)
- BNB → USDC (1-hop)
- Any BEP-20 → USDC via best route

Every swap:
1. Checks liquidity/price quote
2. Verifies slippage tolerance
3. Executes real on-chain transaction
4. Returns TX hash as proof
5. Logs to audit trail

NO SIMULATION. Only real market execution.
"""

import os
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from database.mongodb import get_database

logger = logging.getLogger("dex_swap")

# BSC Contract Addresses
NENO_CONTRACT = "0xeF3F5C1892A8d7A3304E4A15959E124402d69974"
WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
USDC_BSC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
USDT_BSC = "0x55d398326f99059fF775485246999027B3197955"
BUSD = "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"
PANCAKE_ROUTER_V2 = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
PANCAKE_FACTORY_V2 = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"

# PancakeSwap Router V2 ABI (minimal)
ROUTER_ABI = [
    {"inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "path", "type": "address[]"}],
     "name": "getAmountsOut", "outputs": [{"name": "amounts", "type": "uint256[]"}],
     "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "amountOutMin", "type": "uint256"},
                {"name": "path", "type": "address[]"}, {"name": "to", "type": "address"},
                {"name": "deadline", "type": "uint256"}],
     "name": "swapExactTokensForTokens",
     "outputs": [{"name": "amounts", "type": "uint256[]"}],
     "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "amountOutMin", "type": "uint256"},
                {"name": "path", "type": "address[]"}, {"name": "to", "type": "address"},
                {"name": "deadline", "type": "uint256"}],
     "name": "swapExactETHForTokens",
     "outputs": [{"name": "amounts", "type": "uint256[]"}],
     "stateMutability": "payable", "type": "function"},
]

FACTORY_ABI = [
    {"inputs": [{"name": "tokenA", "type": "address"}, {"name": "tokenB", "type": "address"}],
     "name": "getPair", "outputs": [{"type": "address"}],
     "stateMutability": "view", "type": "function"},
]

ERC20_ABI = [
    {"inputs": [{"name": "account", "type": "address"}], "name": "balanceOf",
     "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "name": "approve", "outputs": [{"type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
     "name": "allowance", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
]

MAX_SLIPPAGE_PCT = 3.0
DEADLINE_SECONDS = 300

BSC_RPCS = [
    "https://bsc-dataseed1.binance.org",
    "https://bsc-dataseed2.binance.org",
    "https://bsc-dataseed3.binance.org",
]


class DexSwapService:
    """Real on-chain DEX swap execution via PancakeSwap V2."""

    _instance = None
    _lock = asyncio.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_web3(self):
        rpc = os.environ.get("BSC_RPC_URL", "")
        rpcs = ([rpc] if rpc else []) + BSC_RPCS
        for url in rpcs:
            if not url:
                continue
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 10}))
                if w3.is_connected():
                    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    return w3
            except Exception:
                continue
        return None

    def _get_hot_wallet(self):
        from services.execution_engine import ExecutionEngine
        engine = ExecutionEngine.get_instance()
        return engine._hot_wallet, engine._hot_key

    # ─────────────────────────────────────────────
    #  LIQUIDITY CHECK
    # ─────────────────────────────────────────────

    async def check_liquidity(self, token_address: str, pair_with: str = None) -> dict:
        """
        Check if a token has a PancakeSwap V2 liquidity pool.
        Returns pool address and reserves if found.
        """
        w3 = self._get_web3()
        if not w3:
            return {"has_liquidity": False, "error": "No BSC connection"}

        pair_token = Web3.to_checksum_address(pair_with or WBNB)
        token = Web3.to_checksum_address(token_address)

        try:
            factory = w3.eth.contract(
                address=Web3.to_checksum_address(PANCAKE_FACTORY_V2),
                abi=FACTORY_ABI,
            )
            pair_address = factory.functions.getPair(token, pair_token).call()

            if pair_address == "0x0000000000000000000000000000000000000000":
                return {"has_liquidity": False, "pair": None, "token": token_address}

            return {
                "has_liquidity": True,
                "pair_address": pair_address,
                "token": token_address,
                "pair_with": pair_with or "WBNB",
            }
        except Exception as e:
            return {"has_liquidity": False, "error": str(e)}

    # ─────────────────────────────────────────────
    #  PRICE QUOTE
    # ─────────────────────────────────────────────

    async def get_swap_quote(
        self,
        from_token: str,
        to_token: str,
        amount: float,
        from_decimals: int = 18,
        to_decimals: int = 18,
    ) -> dict:
        """
        Get real PancakeSwap V2 price quote.
        Uses router.getAmountsOut for accurate pricing.
        """
        w3 = self._get_web3()
        if not w3:
            return {"success": False, "error": "No BSC connection"}

        try:
            router = w3.eth.contract(
                address=Web3.to_checksum_address(PANCAKE_ROUTER_V2),
                abi=ROUTER_ABI,
            )

            amount_in = int(Decimal(str(amount)) * Decimal(10 ** from_decimals))
            from_addr = Web3.to_checksum_address(from_token)
            to_addr = Web3.to_checksum_address(to_token)

            # Try direct path first
            paths_to_try = [
                [from_addr, to_addr],
                [from_addr, Web3.to_checksum_address(WBNB), to_addr],
            ]

            best_out = 0
            best_path = None

            for path in paths_to_try:
                try:
                    amounts = router.functions.getAmountsOut(amount_in, path).call()
                    out = amounts[-1]
                    if out > best_out:
                        best_out = out
                        best_path = path
                except Exception:
                    continue

            if best_out == 0 or best_path is None:
                return {
                    "success": False,
                    "error": "No liquidity found for this pair",
                    "from": from_token,
                    "to": to_token,
                    "amount": amount,
                }

            output_amount = float(Decimal(best_out) / Decimal(10 ** to_decimals))
            rate = output_amount / amount if amount > 0 else 0

            return {
                "success": True,
                "from_token": from_token,
                "to_token": to_token,
                "amount_in": amount,
                "amount_out": round(output_amount, 8),
                "rate": round(rate, 8),
                "path": [addr for addr in best_path],
                "hops": len(best_path) - 1,
                "dex": "PancakeSwap V2",
                "slippage_max": MAX_SLIPPAGE_PCT,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─────────────────────────────────────────────
    #  EXECUTE SWAP (REAL ON-CHAIN)
    # ─────────────────────────────────────────────

    async def execute_swap(
        self,
        from_token: str,
        to_token: str,
        amount: float,
        from_decimals: int = 18,
        to_decimals: int = 18,
        slippage_pct: float = MAX_SLIPPAGE_PCT,
    ) -> dict:
        """
        Execute REAL on-chain swap via PancakeSwap V2.
        Returns TX hash or error.
        """
        w3 = self._get_web3()
        hot_wallet, hot_key = self._get_hot_wallet()
        if not w3 or not hot_wallet or not hot_key:
            return {"success": False, "error": "No web3 or hot wallet"}

        # Get quote first
        quote = await self.get_swap_quote(from_token, to_token, amount, from_decimals, to_decimals)
        if not quote.get("success"):
            return {"success": False, "error": f"Quote failed: {quote.get('error')}", "quote": quote}

        amount_in = int(Decimal(str(amount)) * Decimal(10 ** from_decimals))
        min_out = int(Decimal(str(quote["amount_out"])) * Decimal(10 ** to_decimals) * Decimal(1 - slippage_pct / 100))
        path = [Web3.to_checksum_address(a) for a in quote["path"]]
        deadline = w3.eth.get_block("latest")["timestamp"] + DEADLINE_SECONDS

        try:
            async with self._lock:
                router = w3.eth.contract(
                    address=Web3.to_checksum_address(PANCAKE_ROUTER_V2),
                    abi=ROUTER_ABI,
                )

                # Approve token for router (if not BNB)
                from_addr = Web3.to_checksum_address(from_token)
                token_contract = w3.eth.contract(address=from_addr, abi=ERC20_ABI)

                current_allowance = token_contract.functions.allowance(
                    Web3.to_checksum_address(hot_wallet),
                    Web3.to_checksum_address(PANCAKE_ROUTER_V2),
                ).call()

                if current_allowance < amount_in:
                    # Approve max
                    approve_tx = token_contract.functions.approve(
                        Web3.to_checksum_address(PANCAKE_ROUTER_V2),
                        2**256 - 1,
                    ).build_transaction({
                        "chainId": 56,
                        "gas": 60000,
                        "gasPrice": w3.eth.gas_price,
                        "nonce": w3.eth.get_transaction_count(hot_wallet, "pending"),
                        "from": hot_wallet,
                    })
                    signed_approve = w3.eth.account.sign_transaction(approve_tx, hot_key)
                    approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
                    w3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)
                    logger.info(f"[DEX] Approved {from_token[:10]}... for PancakeSwap Router")

                # Execute swap
                swap_tx = router.functions.swapExactTokensForTokens(
                    amount_in, min_out, path,
                    Web3.to_checksum_address(hot_wallet),
                    deadline,
                ).build_transaction({
                    "chainId": 56,
                    "gas": 300000,
                    "gasPrice": w3.eth.gas_price,
                    "nonce": w3.eth.get_transaction_count(hot_wallet, "pending"),
                    "from": hot_wallet,
                })
                signed_swap = w3.eth.account.sign_transaction(swap_tx, hot_key)
                tx_hash = w3.eth.send_raw_transaction(signed_swap.raw_transaction)
                tx_hash_hex = tx_hash.hex()

            logger.info(f"[DEX] Swap TX sent: {tx_hash_hex}")

            # Wait for confirmation
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            success = receipt["status"] == 1

            result = {
                "success": success,
                "tx_hash": tx_hash_hex,
                "explorer": f"https://bscscan.com/tx/{tx_hash_hex}",
                "from_token": from_token,
                "to_token": to_token,
                "amount_in": amount,
                "expected_out": quote["amount_out"],
                "slippage_pct": slippage_pct,
                "path": quote["path"],
                "dex": "PancakeSwap V2",
                "gas_used": receipt.get("gasUsed"),
                "block": receipt.get("blockNumber"),
            }

            # Log to audit
            await self._log_swap(result)

            return result

        except Exception as e:
            error_str = str(e)
            logger.error(f"[DEX] Swap execution failed: {error_str}")

            # Log failure
            await self._log_swap({
                "success": False,
                "error": error_str,
                "from_token": from_token,
                "to_token": to_token,
                "amount_in": amount,
            })

            return {"success": False, "error": error_str}

    async def execute_bnb_to_usdc(self, bnb_amount: float) -> dict:
        """Swap BNB → USDC via PancakeSwap (native BNB swap)."""
        w3 = self._get_web3()
        hot_wallet, hot_key = self._get_hot_wallet()
        if not w3 or not hot_wallet or not hot_key:
            return {"success": False, "error": "No web3 or hot wallet"}

        try:
            router = w3.eth.contract(
                address=Web3.to_checksum_address(PANCAKE_ROUTER_V2),
                abi=ROUTER_ABI,
            )

            amount_in = w3.to_wei(bnb_amount, "ether")
            path = [Web3.to_checksum_address(WBNB), Web3.to_checksum_address(USDC_BSC)]

            # Get quote
            amounts = router.functions.getAmountsOut(amount_in, path).call()
            expected_out = float(Decimal(amounts[-1]) / Decimal(10**18))
            min_out = int(amounts[-1] * (100 - MAX_SLIPPAGE_PCT) / 100)
            deadline = w3.eth.get_block("latest")["timestamp"] + DEADLINE_SECONDS

            async with self._lock:
                swap_tx = router.functions.swapExactETHForTokens(
                    min_out, path,
                    Web3.to_checksum_address(hot_wallet),
                    deadline,
                ).build_transaction({
                    "chainId": 56,
                    "gas": 200000,
                    "gasPrice": w3.eth.gas_price,
                    "nonce": w3.eth.get_transaction_count(hot_wallet, "pending"),
                    "from": hot_wallet,
                    "value": amount_in,
                })
                signed = w3.eth.account.sign_transaction(swap_tx, hot_key)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                tx_hash_hex = tx_hash.hex()

            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            result = {
                "success": receipt["status"] == 1,
                "tx_hash": tx_hash_hex,
                "explorer": f"https://bscscan.com/tx/{tx_hash_hex}",
                "from": "BNB",
                "to": "USDC",
                "amount_in": bnb_amount,
                "expected_out": round(expected_out, 6),
                "dex": "PancakeSwap V2",
                "gas_used": receipt.get("gasUsed"),
            }
            await self._log_swap(result)
            return result

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─────────────────────────────────────────────
    #  FULL PIPELINE: NENO → USDC
    # ─────────────────────────────────────────────

    async def convert_neno_to_usdc(self, neno_amount: float) -> dict:
        """
        Full conversion pipeline: NENO → WBNB → USDC.
        Checks liquidity first, then executes if conditions met.
        """
        # Step 1: Check NENO/WBNB liquidity
        liquidity = await self.check_liquidity(NENO_CONTRACT, WBNB)

        if not liquidity.get("has_liquidity"):
            return {
                "success": False,
                "reason": "no_liquidity",
                "message": "No NENO/WBNB liquidity pool on PancakeSwap V2. Cannot execute real swap.",
                "action": "accumulated_in_treasury",
                "neno_amount": neno_amount,
            }

        # Step 2: Get quote
        quote = await self.get_swap_quote(
            NENO_CONTRACT, USDC_BSC, neno_amount,
            from_decimals=18, to_decimals=18,
        )

        if not quote.get("success"):
            return {
                "success": False,
                "reason": "no_route",
                "message": f"No viable swap route: {quote.get('error')}",
                "neno_amount": neno_amount,
            }

        # Step 3: Execute real swap
        result = await self.execute_swap(
            NENO_CONTRACT, USDC_BSC, neno_amount,
            from_decimals=18, to_decimals=18,
        )

        return result

    # ─────────────────────────────────────────────
    #  AUDIT
    # ─────────────────────────────────────────────

    async def _log_swap(self, data: dict):
        db = get_database()
        await db.dex_swap_log.insert_one({
            "id": str(uuid.uuid4()),
            **{k: v for k, v in data.items() if k != "_id"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def get_swap_history(self, limit: int = 50) -> list:
        db = get_database()
        return await db.dex_swap_log.find(
            {}, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)

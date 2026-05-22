"""
Execution Engine — NeoNoble Ramp.

Real on-chain transaction signing and execution.
Signs with hot wallet private key, sends real BEP-20 transfers.
Multi-DEX routing via PancakeSwap.
"""

import os
import uuid
import logging
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account

logger = logging.getLogger(__name__)

NENO_CONTRACT = "0xeF3F5C1892A8d7A3304E4A15959E124402d69974"
NENO_DECIMALS = 18
WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
BUSD = "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"
USDT_BSC = "0x55d398326f99059fF775485246999027B3197955"
USDC_BSC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
PANCAKE_ROUTER_V2 = "0x10ED43C718714eb63d5aA57B78B54704E256024E"

# Binance-Peg wrapped tokens on BSC (real value, tradable on PancakeSwap)
WETH_BSC = "0x2170Ed0880ac9A755fd29B2688956BD959F933F8"  # Binance-Peg ETH
BTCB_BSC = "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c"  # Binance-Peg BTCB

# Map internal asset names to BSC BEP-20 contract addresses
ASSET_TO_BSC_CONTRACT = {
    "NENO": NENO_CONTRACT,
    "USDT": USDT_BSC,
    "USDC": USDC_BSC,
    "ETH": WETH_BSC,
    "BTC": BTCB_BSC,
}
ASSET_DECIMALS = {
    "NENO": 18, "USDT": 18, "USDC": 18, "ETH": 18, "BTC": 18,
}

ERC20_ABI = [
    {"inputs": [{"name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}], "name": "transfer", "outputs": [{"type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}], "name": "approve", "outputs": [{"type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}], "name": "allowance", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
]

BSC_RPCS = [
    "https://bsc-dataseed1.binance.org",
    "https://bsc-dataseed2.binance.org",
    "https://bsc-dataseed3.binance.org",
]


class ExecutionEngine:
    """Real on-chain execution with hot wallet signing."""

    _instance = None

    def __init__(self):
        self._w3 = None
        self._hot_wallet = None
        self._hot_key = None
        self._nonce_lock = asyncio.Lock()
        self._init_wallets()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _init_wallets(self):
        mnemonic = os.environ.get("NENO_WALLET_MNEMONIC")
        pk = os.environ.get("CONVERSION_WALLET_PRIVATE_KEY")
        if mnemonic:
            Account.enable_unaudited_hdwallet_features()
            acct = Account.from_mnemonic(mnemonic)
            self._hot_wallet = acct.address
            self._hot_key = acct.key.hex()
            logger.info(f"[EXEC] Hot wallet loaded: {self._hot_wallet} (key: ***masked***)")
        elif pk:
            acct = Account.from_key(pk)
            self._hot_wallet = acct.address
            self._hot_key = pk
            logger.info(f"[EXEC] Hot wallet from PK: {self._hot_wallet} (key: ***masked***)")

    def _get_web3(self) -> Optional[Web3]:
        if self._w3 and self._w3.is_connected():
            return self._w3
        rpc = os.environ.get("BSC_RPC_URL", "")
        rpcs = ([rpc] if rpc else []) + BSC_RPCS
        for url in rpcs:
            if not url:
                continue
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 10}))
                if w3.is_connected():
                    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                    self._w3 = w3
                    return w3
            except Exception:
                continue
        return None

    @property
    def hot_wallet(self):
        return self._hot_wallet

    async def get_hot_wallet_status(self) -> dict:
        """Get real on-chain balances of hot wallet."""
        w3 = self._get_web3()
        if not w3 or not self._hot_wallet:
            return {"available": False, "error": "No connection or wallet"}
        try:
            bnb = float(w3.from_wei(w3.eth.get_balance(self._hot_wallet), "ether"))
            contract = w3.eth.contract(address=Web3.to_checksum_address(NENO_CONTRACT), abi=ERC20_ABI)
            neno_raw = contract.functions.balanceOf(self._hot_wallet).call()
            neno = float(Decimal(neno_raw) / Decimal(10 ** NENO_DECIMALS))
            return {
                "address": self._hot_wallet,
                "bnb_balance": round(bnb, 8),
                "neno_balance": round(neno, 4),
                "gas_sufficient": bnb > 0.001,
                "available": True,
                "chain": "BSC Mainnet",
                "chain_id": 56,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    async def send_neno(self, to_address: str, amount: float) -> dict:
        """Send real NENO tokens from hot wallet to user wallet."""
        w3 = self._get_web3()
        if not w3 or not self._hot_key:
            return {"success": False, "error": "No web3 connection or private key"}

        try:
            to_addr = Web3.to_checksum_address(to_address)
            contract = w3.eth.contract(address=Web3.to_checksum_address(NENO_CONTRACT), abi=ERC20_ABI)
            raw_amount = int(Decimal(str(amount)) * Decimal(10 ** NENO_DECIMALS))

            balance = contract.functions.balanceOf(self._hot_wallet).call()
            if balance < raw_amount:
                return {"success": False, "error": f"Insufficient NENO in hot wallet: {float(Decimal(balance) / Decimal(10**NENO_DECIMALS))} < {amount}"}

            async with self._nonce_lock:
                nonce = w3.eth.get_transaction_count(self._hot_wallet, "pending")
                tx = contract.functions.transfer(to_addr, raw_amount).build_transaction({
                    "chainId": 56,
                    "gas": 100000,
                    "gasPrice": w3.eth.gas_price,
                    "nonce": nonce,
                    "from": self._hot_wallet,
                })
                signed = w3.eth.account.sign_transaction(tx, self._hot_key)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                tx_hash_hex = tx_hash.hex()

            logger.info(f"[EXEC] NENO transfer sent: {amount} to {to_addr} | tx: {tx_hash_hex}")

            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            success = receipt["status"] == 1

            return {
                "success": success,
                "tx_hash": tx_hash_hex,
                "block_number": receipt["blockNumber"],
                "gas_used": receipt["gasUsed"],
                "explorer": f"https://bscscan.com/tx/{tx_hash_hex}",
                "from": self._hot_wallet,
                "to": to_addr,
                "amount": amount,
                "asset": "NENO",
            }
        except Exception as e:
            logger.error(f"[EXEC] NENO transfer failed: {e}")
            return {"success": False, "error": str(e)}

    async def send_bnb(self, to_address: str, amount_bnb: float) -> dict:
        """Send real BNB from hot wallet."""
        w3 = self._get_web3()
        if not w3 or not self._hot_key:
            return {"success": False, "error": "No connection or key"}

        try:
            to_addr = Web3.to_checksum_address(to_address)
            value_wei = w3.to_wei(amount_bnb, "ether")

            bnb_balance = w3.eth.get_balance(self._hot_wallet)
            gas_price = w3.eth.gas_price
            gas_cost = gas_price * 21000
            if bnb_balance < value_wei + gas_cost:
                return {"success": False, "error": f"Insufficient BNB: {w3.from_wei(bnb_balance, 'ether')}"}

            async with self._nonce_lock:
                nonce = w3.eth.get_transaction_count(self._hot_wallet, "pending")
                tx = {
                    "to": to_addr, "value": value_wei,
                    "gas": 21000, "gasPrice": gas_price,
                    "nonce": nonce, "chainId": 56,
                }
                signed = w3.eth.account.sign_transaction(tx, self._hot_key)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                tx_hash_hex = tx_hash.hex()

            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            return {
                "success": receipt["status"] == 1,
                "tx_hash": tx_hash_hex,
                "block_number": receipt["blockNumber"],
                "explorer": f"https://bscscan.com/tx/{tx_hash_hex}",
                "amount": amount_bnb, "asset": "BNB",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def send_bep20(self, asset: str, to_address: str, amount: float) -> dict:
        """
        Send any BEP-20 token (ETH/BTC/USDT/USDC/NENO) from hot wallet.
        Looks up the contract address automatically from ASSET_TO_BSC_CONTRACT.
        Returns a real tx hash verifiable on BscScan.
        """
        asset_upper = asset.upper()
        contract_addr = ASSET_TO_BSC_CONTRACT.get(asset_upper)
        if not contract_addr:
            return {"success": False, "error": f"Asset {asset} non supportato per trasferimento on-chain BSC"}

        if asset_upper == "NENO":
            return await self.send_neno(to_address, amount)

        w3 = self._get_web3()
        if not w3 or not self._hot_key:
            return {"success": False, "error": "No web3 connection or private key"}

        try:
            to_addr = Web3.to_checksum_address(to_address)
            decimals = ASSET_DECIMALS.get(asset_upper, 18)
            contract = w3.eth.contract(address=Web3.to_checksum_address(contract_addr), abi=ERC20_ABI)
            raw_amount = int(Decimal(str(amount)) * Decimal(10 ** decimals))

            balance = contract.functions.balanceOf(self._hot_wallet).call()
            if balance < raw_amount:
                human_bal = float(Decimal(balance) / Decimal(10 ** decimals))
                return {"success": False, "error": f"Insufficient {asset_upper} in hot wallet: {human_bal} < {amount}"}

            async with self._nonce_lock:
                nonce = w3.eth.get_transaction_count(self._hot_wallet, "pending")
                tx = contract.functions.transfer(to_addr, raw_amount).build_transaction({
                    "chainId": 56,
                    "gas": 100000,
                    "gasPrice": w3.eth.gas_price,
                    "nonce": nonce,
                    "from": self._hot_wallet,
                })
                signed = w3.eth.account.sign_transaction(tx, self._hot_key)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                tx_hash_hex = tx_hash.hex()

            logger.info(f"[EXEC] BEP-20 transfer sent: {amount} {asset_upper} to {to_addr} | tx: {tx_hash_hex}")
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            success = receipt["status"] == 1

            return {
                "success": success,
                "tx_hash": tx_hash_hex,
                "block_number": receipt["blockNumber"],
                "gas_used": receipt["gasUsed"],
                "explorer": f"https://bscscan.com/tx/{tx_hash_hex}",
                "from": self._hot_wallet,
                "to": to_addr,
                "amount": amount,
                "asset": asset_upper,
                "contract": contract_addr,
                "chain": "BSC Mainnet",
            }
        except Exception as e:
            logger.error(f"[EXEC] BEP-20 {asset_upper} transfer failed: {e}")
            return {"success": False, "error": str(e)}

    async def send_asset_real(self, asset: str, to_address: str, amount: float) -> dict:
        """
        Unified real on-chain dispatch: BNB native or any BEP-20.
        This is the single entry point for all real on-chain delivery.
        Also hooks into wallet segregation for USDC operations.
        """
        asset_upper = asset.upper()

        # USDC operations get routed through segregation engine
        if asset_upper == "USDC":
            try:
                from services.wallet_segregation_engine import WalletSegregationEngine
                seg = WalletSegregationEngine.get_instance()
                await seg.record_movement(
                    from_role="treasury",
                    to_role="external",
                    amount_usdc=amount,
                    rule_type="outbound_transfer",
                    metadata={"to_address": to_address, "asset": "USDC"},
                )
            except Exception as e:
                logger.warning(f"[EXEC] USDC segregation log failed: {e}")

        if asset_upper == "BNB":
            return await self.send_bnb(to_address, amount)
        if asset_upper in ASSET_TO_BSC_CONTRACT:
            return await self.send_bep20(asset_upper, to_address, amount)
        return {"success": False, "error": f"Asset {asset} non consegnabile on-chain via BSC"}


class LiquidityEngine:
    """Internal netting + JIT liquidity routing."""

    def __init__(self):
        self._order_book = []  # Pending orders for internal matching

    async def try_internal_match(self, db, order_type: str, asset: str, amount: float, price_eur: float) -> Optional[dict]:
        """Try to match order internally against other users' pending orders."""
        opposite = "sell" if order_type == "buy" else "buy"
        match = await db.internal_order_book.find_one_and_update(
            {"type": opposite, "asset": asset, "amount": {"$gte": amount}, "status": "pending"},
            {"$set": {"status": "matched", "matched_at": datetime.now(timezone.utc).isoformat()}},
        )
        if match:
            logger.info(f"[NETTING] Internal match: {order_type} {amount} {asset} matched with order {match.get('id')}")
            return {
                "matched": True, "counterparty_order": str(match.get("id", "")),
                "internalized": True, "savings_eur": round(amount * price_eur * 0.003, 4),
            }
        return None

    async def submit_order(self, db, user_id: str, order_type: str, asset: str, amount: float, price_eur: float) -> str:
        """Submit order to internal book for potential matching."""
        order_id = str(uuid.uuid4())
        await db.internal_order_book.insert_one({
            "_id": order_id, "id": order_id, "user_id": user_id,
            "type": order_type, "asset": asset, "amount": amount,
            "price_eur": price_eur, "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return order_id

    def calculate_routing(self, from_asset: str, to_asset: str, amount: float) -> dict:
        """Calculate optimal routing path."""
        if from_asset == "NENO" and to_asset in ("BNB", "WBNB"):
            return {"path": [NENO_CONTRACT, WBNB], "dex": "PancakeSwap V2", "hops": 1}
        elif from_asset == "NENO":
            return {"path": [NENO_CONTRACT, WBNB, BUSD], "dex": "PancakeSwap V2", "hops": 2}
        return {"path": ["direct"], "dex": "internal", "hops": 0}


class TreasuryEngine:
    """PnL tracking, fee collection, risk management."""

    async def record_fee(self, db, tx_id: str, fee_amount: float, fee_asset: str, tx_type: str):
        """Record platform fee in treasury."""
        await db.treasury_fees.insert_one({
            "id": str(uuid.uuid4()), "tx_id": tx_id, "fee_amount": fee_amount,
            "fee_asset": fee_asset, "tx_type": tx_type,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })

    async def get_pnl(self, db) -> dict:
        """Get current P&L snapshot."""
        pipeline = [
            {"$group": {"_id": "$fee_asset", "total_fees": {"$sum": "$fee_amount"}, "count": {"$sum": 1}}}
        ]
        results = await db.treasury_fees.aggregate(pipeline).to_list(100)
        total_eur = sum(r["total_fees"] for r in results if r["_id"] == "EUR")
        return {
            "total_fees_eur": round(total_eur, 2),
            "by_asset": {r["_id"]: {"total": round(r["total_fees"], 8), "tx_count": r["count"]} for r in results},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def get_hot_wallet_risk(self, db) -> dict:
        """Assess hot wallet risk exposure."""
        engine = ExecutionEngine.get_instance()
        status = await engine.get_hot_wallet_status()
        pending_payouts = await db.payout_queue.count_documents({"state": "payout_pending"})
        pending_amount = 0
        async for p in db.payout_queue.find({"state": "payout_pending"}):
            pending_amount += p.get("amount", 0)

        return {
            "hot_wallet": status,
            "pending_payouts": pending_payouts,
            "pending_payout_amount_eur": round(pending_amount, 2),
            "risk_level": "high" if pending_amount > 100000 else "medium" if pending_amount > 10000 else "low",
        }

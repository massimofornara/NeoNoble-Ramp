"""
DEX Service - Real On-Chain Swap Execution.

Provides real DEX integration for C-SAFE off-ramp:
- 1inch Aggregator API (primary - best execution)
- PancakeSwap V3 Router (fallback)
- Slippage protection with minOut enforcement
- Full audit logging per swap

IMPORTANT: This is REAL execution, not simulation.
All swaps are executed on BSC mainnet.
"""

import os
import logging
import aiohttp
import asyncio
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime, timezone
from uuid import uuid4
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from web3 import Web3, AsyncWeb3
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# BSC Network Configuration
BSC_RPC_URL = os.environ.get('BSC_RPC_URL', 'https://bsc-dataseed.binance.org/')
BSC_CHAIN_ID = 56

# Token Addresses on BSC
NENO_ADDRESS = os.environ.get('NENO_CONTRACT_ADDRESS', '0xeF3F5C1892A8d7A3304E4A15959E124402d69974')
WBNB_ADDRESS = '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c'
USDT_ADDRESS = '0x55d398326f99059fF775485246999027B3197955'
USDC_ADDRESS = '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d'
BUSD_ADDRESS = '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56'

# Token Decimals
TOKEN_DECIMALS = {
    NENO_ADDRESS.lower(): 18,
    WBNB_ADDRESS.lower(): 18,
    USDT_ADDRESS.lower(): 18,
    USDC_ADDRESS.lower(): 18,
    BUSD_ADDRESS.lower(): 18
}

# Router Addresses
PANCAKESWAP_V3_ROUTER = '0x13f4EA83D0bd40E75C8222255bc855a974568Dd4'
ONEINCH_ROUTER_V5 = '0x1111111254EEB25477B68fb85Ed929f73A960582'

# 1inch API
ONEINCH_API_URL = 'https://api.1inch.dev/swap/v6.0/56'
ONEINCH_API_KEY = os.environ.get('ONEINCH_API_KEY', '')


class SwapStatus(str, Enum):
    """Swap execution status."""
    PENDING = "pending"
    QUOTING = "quoting"
    APPROVED = "approved"
    EXECUTING = "executing"
    CONFIRMING = "confirming"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class SwapQuote:
    """Quote for a DEX swap."""
    quote_id: str
    source_token: str
    destination_token: str
    source_amount: int  # In wei
    destination_amount: int  # In wei (estimated)
    source_amount_decimal: float
    destination_amount_decimal: float
    exchange_rate: float
    price_impact_pct: float
    gas_estimate: int
    gas_price_gwei: float
    estimated_gas_cost_bnb: float
    estimated_gas_cost_eur: float
    router: str  # '1inch' or 'pancakeswap'
    route_path: List[str]
    valid_until: str
    created_at: str


@dataclass 
class SwapResult:
    """Result of a DEX swap execution."""
    swap_id: str
    quote_id: str
    status: SwapStatus
    source_token: str
    destination_token: str
    source_amount: int
    destination_amount: int
    source_amount_decimal: float
    destination_amount_decimal: float
    actual_rate: float
    slippage_pct: float
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    gas_used: int = 0
    gas_price_gwei: float = 0
    gas_cost_bnb: float = 0
    gas_cost_eur: float = 0
    router: str = ""
    route_path: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None


class DEXService:
    """
    DEX Service for real on-chain swap execution.
    
    Features:
    - 1inch Aggregator integration (best execution)
    - PancakeSwap V3 fallback
    - Slippage protection
    - Gas estimation and optimization
    - Full audit trail
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.swaps_collection = db.dex_swaps
        self.quotes_collection = db.dex_quotes
        self.config_collection = db.dex_config
        
        self._initialized = False
        self._web3: Optional[AsyncWeb3] = None
        self._conversion_wallet_address: Optional[str] = None
        self._conversion_wallet_key: Optional[str] = None
        self._settlement_wallet_address: Optional[str] = None
        
        # Configuration
        self._enabled = False
        self._max_slippage_pct = 2.0
        self._min_liquidity_depth_eur = 10000.0
        self._max_price_impact_pct = 1.0
        self._whitelisted_accounts: List[str] = []
        self._daily_cap_eur = 300.0
        self._daily_volume_eur = 0.0
        self._last_reset_date: Optional[str] = None
    
    async def initialize(self):
        """Initialize DEX service."""
        if self._initialized:
            return
        
        # Create indexes
        await self.swaps_collection.create_index("swap_id", unique=True)
        await self.swaps_collection.create_index("quote_id")
        await self.swaps_collection.create_index("tx_hash")
        await self.swaps_collection.create_index("status")
        await self.swaps_collection.create_index("created_at")
        await self.quotes_collection.create_index("quote_id", unique=True)
        
        # Initialize Web3
        try:
            self._web3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(BSC_RPC_URL))
            # Note: Web3 v7 auto-handles PoA chains, no middleware needed
            
            chain_id = await self._web3.eth.chain_id
            if chain_id != BSC_CHAIN_ID:
                logger.warning(f"Connected to chain {chain_id}, expected BSC (56)")
        except Exception as e:
            logger.error(f"Failed to initialize Web3: {e}")
        
        # Load wallet configuration
        self._conversion_wallet_key = os.environ.get('CONVERSION_WALLET_PRIVATE_KEY')
        self._settlement_wallet_address = os.environ.get('SETTLEMENT_WALLET_ADDRESS')
        
        if self._conversion_wallet_key and self._web3:
            try:
                account = self._web3.eth.account.from_key(self._conversion_wallet_key)
                self._conversion_wallet_address = account.address
                logger.info(f"Conversion wallet configured: {self._conversion_wallet_address[:10]}...")
            except Exception as e:
                logger.error(f"Invalid conversion wallet key: {e}")
        
        # Load configuration
        await self._load_config()
        
        self._initialized = True
        logger.info(
            f"DEX Service initialized:\n"
            f"  Enabled: {self._enabled}\n"
            f"  Conversion Wallet: {self._conversion_wallet_address or 'NOT CONFIGURED'}\n"
            f"  Settlement Wallet: {self._settlement_wallet_address or 'NOT CONFIGURED'}\n"
            f"  Max Slippage: {self._max_slippage_pct}%\n"
            f"  Daily Cap: €{self._daily_cap_eur:,.2f}"
        )
    
    async def _load_config(self):
        """Load DEX configuration from database."""
        config = await self.config_collection.find_one({"config_type": "dex"})
        
        if config:
            self._enabled = config.get("enabled", False)
            self._max_slippage_pct = config.get("max_slippage_pct", 2.0)
            self._min_liquidity_depth_eur = config.get("min_liquidity_depth_eur", 10000.0)
            self._max_price_impact_pct = config.get("max_price_impact_pct", 1.0)
            self._whitelisted_accounts = config.get("whitelisted_accounts", [])
            self._daily_cap_eur = config.get("daily_cap_eur", 300.0)
            self._daily_volume_eur = config.get("daily_volume_eur", 0.0)
            self._last_reset_date = config.get("last_reset_date")
        else:
            # Create default config
            await self.config_collection.insert_one({
                "config_type": "dex",
                "enabled": False,
                "max_slippage_pct": 2.0,
                "min_liquidity_depth_eur": 10000.0,
                "max_price_impact_pct": 1.0,
                "whitelisted_accounts": [],
                "daily_cap_eur": 300.0,
                "daily_volume_eur": 0.0,
                "last_reset_date": datetime.now(timezone.utc).date().isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        
        # Reset daily volume if new day
        today = datetime.now(timezone.utc).date().isoformat()
        if self._last_reset_date != today:
            self._daily_volume_eur = 0.0
            await self.config_collection.update_one(
                {"config_type": "dex"},
                {"$set": {"daily_volume_eur": 0.0, "last_reset_date": today}}
            )
    
    def is_enabled(self) -> bool:
        """Check if DEX service is enabled."""
        return self._enabled and self._conversion_wallet_key is not None
    
    def check_daily_cap(self, amount_eur: float) -> Tuple[bool, str]:
        """Check if amount is within daily cap."""
        if self._daily_volume_eur + amount_eur > self._daily_cap_eur:
            remaining = self._daily_cap_eur - self._daily_volume_eur
            return False, f"Daily cap exceeded. Remaining: €{remaining:,.2f}"
        return True, ""
    
    def is_whitelisted(self, user_id: str) -> bool:
        """Check if user is whitelisted for real DEX swaps."""
        return len(self._whitelisted_accounts) == 0 or user_id in self._whitelisted_accounts
    
    async def get_quote_1inch(
        self,
        source_token: str,
        destination_token: str,
        amount_wei: int
    ) -> Optional[SwapQuote]:
        """Get swap quote from 1inch Aggregator."""
        try:
            now = datetime.now(timezone.utc)
            
            # 1inch API v6.0 quote endpoint
            url = f"{ONEINCH_API_URL}/quote"
            params = {
                "src": source_token,
                "dst": destination_token,
                "amount": str(amount_wei),
                "includeGas": "true"
            }
            
            headers = {
                "accept": "application/json"
            }
            if ONEINCH_API_KEY:
                headers["Authorization"] = f"Bearer {ONEINCH_API_KEY}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.warning(f"1inch quote failed: {response.status} - {error_text}")
                        return None
                    
                    data = await response.json()
            
            # Parse response
            dst_amount = int(data.get("dstAmount", 0))
            gas_estimate = int(data.get("gas", 300000))
            
            # Get decimals
            src_decimals = TOKEN_DECIMALS.get(source_token.lower(), 18)
            dst_decimals = TOKEN_DECIMALS.get(destination_token.lower(), 18)
            
            src_amount_dec = amount_wei / (10 ** src_decimals)
            dst_amount_dec = dst_amount / (10 ** dst_decimals)
            
            # Calculate exchange rate
            exchange_rate = dst_amount_dec / src_amount_dec if src_amount_dec > 0 else 0
            
            # Get gas price
            gas_price = await self._web3.eth.gas_price if self._web3 else 5_000_000_000
            gas_price_gwei = gas_price / 1e9
            gas_cost_bnb = (gas_estimate * gas_price) / 1e18
            gas_cost_eur = gas_cost_bnb * 300  # Approximate BNB price
            
            # Estimate price impact (simplified)
            price_impact = 0.1  # 1inch doesn't always provide this directly
            
            quote = SwapQuote(
                quote_id=f"1inch_{uuid4().hex[:12]}",
                source_token=source_token,
                destination_token=destination_token,
                source_amount=amount_wei,
                destination_amount=dst_amount,
                source_amount_decimal=src_amount_dec,
                destination_amount_decimal=dst_amount_dec,
                exchange_rate=exchange_rate,
                price_impact_pct=price_impact,
                gas_estimate=gas_estimate,
                gas_price_gwei=gas_price_gwei,
                estimated_gas_cost_bnb=gas_cost_bnb,
                estimated_gas_cost_eur=gas_cost_eur,
                router="1inch",
                route_path=data.get("protocols", [[]])[0] if data.get("protocols") else [],
                valid_until=(now.timestamp() + 30).__str__(),
                created_at=now.isoformat()
            )
            
            # Store quote
            await self.quotes_collection.insert_one({
                "quote_id": quote.quote_id,
                "router": "1inch",
                "source_token": source_token,
                "destination_token": destination_token,
                "source_amount": amount_wei,
                "destination_amount": dst_amount,
                "raw_response": data,
                "created_at": now.isoformat()
            })
            
            logger.info(
                f"[1INCH] Quote: {src_amount_dec:.6f} → {dst_amount_dec:.6f} | "
                f"Rate: {exchange_rate:.6f} | Gas: {gas_cost_eur:.2f} EUR"
            )
            
            return quote
            
        except Exception as e:
            logger.error(f"1inch quote error: {e}")
            return None
    
    async def get_quote_pancakeswap(
        self,
        source_token: str,
        destination_token: str,
        amount_wei: int
    ) -> Optional[SwapQuote]:
        """Get swap quote from PancakeSwap V3 (fallback)."""
        try:
            now = datetime.now(timezone.utc)
            
            if not self._web3:
                return None
            
            # PancakeSwap V3 Quoter contract
            QUOTER_ADDRESS = '0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997'
            QUOTER_ABI = [
                {
                    "inputs": [
                        {"name": "tokenIn", "type": "address"},
                        {"name": "tokenOut", "type": "address"},
                        {"name": "amountIn", "type": "uint256"},
                        {"name": "fee", "type": "uint24"},
                        {"name": "sqrtPriceLimitX96", "type": "uint160"}
                    ],
                    "name": "quoteExactInputSingle",
                    "outputs": [
                        {"name": "amountOut", "type": "uint256"},
                        {"name": "sqrtPriceX96After", "type": "uint160"},
                        {"name": "initializedTicksCrossed", "type": "uint32"},
                        {"name": "gasEstimate", "type": "uint256"}
                    ],
                    "stateMutability": "nonpayable",
                    "type": "function"
                }
            ]
            
            quoter = self._web3.eth.contract(address=QUOTER_ADDRESS, abi=QUOTER_ABI)
            
            # Try different fee tiers
            fee_tiers = [500, 2500, 10000]  # 0.05%, 0.25%, 1%
            best_quote = None
            best_amount = 0
            
            for fee in fee_tiers:
                try:
                    result = await quoter.functions.quoteExactInputSingle(
                        source_token,
                        destination_token,
                        amount_wei,
                        fee,
                        0
                    ).call()
                    
                    if result[0] > best_amount:
                        best_amount = result[0]
                        best_quote = {
                            "amountOut": result[0],
                            "gasEstimate": result[3],
                            "fee": fee
                        }
                except Exception:
                    continue
            
            if not best_quote:
                return None
            
            dst_amount = best_quote["amountOut"]
            gas_estimate = best_quote["gasEstimate"] or 300000
            
            # Get decimals
            src_decimals = TOKEN_DECIMALS.get(source_token.lower(), 18)
            dst_decimals = TOKEN_DECIMALS.get(destination_token.lower(), 18)
            
            src_amount_dec = amount_wei / (10 ** src_decimals)
            dst_amount_dec = dst_amount / (10 ** dst_decimals)
            
            exchange_rate = dst_amount_dec / src_amount_dec if src_amount_dec > 0 else 0
            
            gas_price = await self._web3.eth.gas_price
            gas_price_gwei = gas_price / 1e9
            gas_cost_bnb = (gas_estimate * gas_price) / 1e18
            gas_cost_eur = gas_cost_bnb * 300
            
            quote = SwapQuote(
                quote_id=f"pcs_{uuid4().hex[:12]}",
                source_token=source_token,
                destination_token=destination_token,
                source_amount=amount_wei,
                destination_amount=dst_amount,
                source_amount_decimal=src_amount_dec,
                destination_amount_decimal=dst_amount_dec,
                exchange_rate=exchange_rate,
                price_impact_pct=0.5,  # Estimate
                gas_estimate=gas_estimate,
                gas_price_gwei=gas_price_gwei,
                estimated_gas_cost_bnb=gas_cost_bnb,
                estimated_gas_cost_eur=gas_cost_eur,
                router="pancakeswap",
                route_path=[source_token, destination_token],
                valid_until=(now.timestamp() + 30).__str__(),
                created_at=now.isoformat()
            )
            
            logger.info(
                f"[PANCAKESWAP] Quote: {src_amount_dec:.6f} → {dst_amount_dec:.6f} | "
                f"Rate: {exchange_rate:.6f}"
            )
            
            return quote
            
        except Exception as e:
            logger.error(f"PancakeSwap quote error: {e}")
            return None
    
    async def get_best_quote(
        self,
        source_token: str,
        destination_token: str,
        amount_wei: int
    ) -> Optional[SwapQuote]:
        """Get best quote from all available routers."""
        quotes = []
        
        # Try 1inch first (usually better)
        quote_1inch = await self.get_quote_1inch(source_token, destination_token, amount_wei)
        if quote_1inch:
            quotes.append(quote_1inch)
        
        # Try PancakeSwap as fallback
        quote_pcs = await self.get_quote_pancakeswap(source_token, destination_token, amount_wei)
        if quote_pcs:
            quotes.append(quote_pcs)
        
        if not quotes:
            return None
        
        # Return best quote (highest destination amount)
        return max(quotes, key=lambda q: q.destination_amount)
    
    async def execute_swap_1inch(
        self,
        source_token: str,
        destination_token: str,
        amount_wei: int,
        min_return: int,
        quote_id: str
    ) -> SwapResult:
        """Execute swap via 1inch Aggregator."""
        swap_id = f"swap_{uuid4().hex[:12]}"
        
        result = SwapResult(
            swap_id=swap_id,
            quote_id=quote_id,
            status=SwapStatus.PENDING,
            source_token=source_token,
            destination_token=destination_token,
            source_amount=amount_wei,
            destination_amount=0,
            source_amount_decimal=0,
            destination_amount_decimal=0,
            actual_rate=0,
            slippage_pct=0,
            router="1inch"
        )
        
        try:
            if not self._web3 or not self._conversion_wallet_key:
                result.status = SwapStatus.FAILED
                result.error_message = "Web3 or wallet not configured"
                return result
            
            result.status = SwapStatus.QUOTING
            
            # Get swap data from 1inch
            url = f"{ONEINCH_API_URL}/swap"
            params = {
                "src": source_token,
                "dst": destination_token,
                "amount": str(amount_wei),
                "from": self._conversion_wallet_address,
                "slippage": str(self._max_slippage_pct),
                "disableEstimate": "false"
            }
            
            headers = {"accept": "application/json"}
            if ONEINCH_API_KEY:
                headers["Authorization"] = f"Bearer {ONEINCH_API_KEY}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        result.status = SwapStatus.FAILED
                        result.error_message = f"1inch swap API failed: {error_text}"
                        return result
                    
                    swap_data = await response.json()
            
            # Verify min return
            dst_amount = int(swap_data.get("dstAmount", 0))
            if dst_amount < min_return:
                result.status = SwapStatus.FAILED
                result.error_message = f"Output {dst_amount} below minReturn {min_return}"
                return result
            
            result.status = SwapStatus.APPROVED
            
            # Build transaction
            tx_data = swap_data.get("tx", {})
            
            # Check allowance and approve if needed
            await self._ensure_token_approval(source_token, amount_wei, tx_data.get("to"))
            
            result.status = SwapStatus.EXECUTING
            
            # Send transaction
            account = self._web3.eth.account.from_key(self._conversion_wallet_key)
            
            tx = {
                "from": account.address,
                "to": Web3.to_checksum_address(tx_data.get("to")),
                "data": tx_data.get("data"),
                "value": int(tx_data.get("value", 0)),
                "gas": int(tx_data.get("gas", 500000)),
                "gasPrice": await self._web3.eth.gas_price,
                "nonce": await self._web3.eth.get_transaction_count(account.address),
                "chainId": BSC_CHAIN_ID
            }
            
            signed_tx = account.sign_transaction(tx)
            tx_hash = await self._web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            result.tx_hash = tx_hash.hex()
            result.status = SwapStatus.CONFIRMING
            
            logger.info(f"[1INCH] Swap tx sent: {result.tx_hash}")
            
            # Wait for confirmation
            receipt = await self._web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            if receipt.status == 1:
                result.status = SwapStatus.COMPLETED
                result.block_number = receipt.blockNumber
                result.gas_used = receipt.gasUsed
                result.gas_price_gwei = tx["gasPrice"] / 1e9
                result.gas_cost_bnb = (receipt.gasUsed * tx["gasPrice"]) / 1e18
                result.gas_cost_eur = result.gas_cost_bnb * 300
                result.destination_amount = dst_amount
                result.completed_at = datetime.now(timezone.utc).isoformat()
                
                # Calculate actual values
                src_decimals = TOKEN_DECIMALS.get(source_token.lower(), 18)
                dst_decimals = TOKEN_DECIMALS.get(destination_token.lower(), 18)
                result.source_amount_decimal = amount_wei / (10 ** src_decimals)
                result.destination_amount_decimal = dst_amount / (10 ** dst_decimals)
                result.actual_rate = result.destination_amount_decimal / result.source_amount_decimal if result.source_amount_decimal > 0 else 0
                
                logger.info(
                    f"[1INCH] Swap COMPLETED: {result.source_amount_decimal:.6f} → "
                    f"{result.destination_amount_decimal:.6f} | Tx: {result.tx_hash}"
                )
            else:
                result.status = SwapStatus.FAILED
                result.error_message = "Transaction reverted"
                logger.error("[1INCH] Swap FAILED: Transaction reverted")
            
        except Exception as e:
            result.status = SwapStatus.FAILED
            result.error_message = str(e)
            logger.error(f"[1INCH] Swap error: {e}")
        
        # Store result
        await self.swaps_collection.insert_one({
            "swap_id": result.swap_id,
            "quote_id": result.quote_id,
            "status": result.status.value,
            "source_token": result.source_token,
            "destination_token": result.destination_token,
            "source_amount": result.source_amount,
            "destination_amount": result.destination_amount,
            "tx_hash": result.tx_hash,
            "block_number": result.block_number,
            "gas_used": result.gas_used,
            "gas_cost_eur": result.gas_cost_eur,
            "router": result.router,
            "error_message": result.error_message,
            "created_at": result.created_at,
            "completed_at": result.completed_at
        })
        
        return result
    
    async def _ensure_token_approval(
        self,
        token_address: str,
        amount: int,
        spender: str
    ):
        """Ensure token approval for router."""
        if not self._web3 or not self._conversion_wallet_key:
            return
        
        # ERC20 ABI for approval
        ERC20_ABI = [
            {
                "constant": True,
                "inputs": [
                    {"name": "_owner", "type": "address"},
                    {"name": "_spender", "type": "address"}
                ],
                "name": "allowance",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function"
            },
            {
                "constant": False,
                "inputs": [
                    {"name": "_spender", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "approve",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function"
            }
        ]
        
        token = self._web3.eth.contract(address=token_address, abi=ERC20_ABI)
        account = self._web3.eth.account.from_key(self._conversion_wallet_key)
        
        # Check current allowance
        current_allowance = await token.functions.allowance(
            account.address,
            spender
        ).call()
        
        if current_allowance >= amount:
            return  # Already approved
        
        # Approve max uint256
        max_approval = 2**256 - 1
        
        tx = await token.functions.approve(spender, max_approval).build_transaction({
            "from": account.address,
            "gas": 100000,
            "gasPrice": await self._web3.eth.gas_price,
            "nonce": await self._web3.eth.get_transaction_count(account.address),
            "chainId": BSC_CHAIN_ID
        })
        
        signed_tx = account.sign_transaction(tx)
        tx_hash = await self._web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        logger.info(f"[DEX] Token approval tx: {tx_hash.hex()}")
        
        # Wait for approval confirmation
        await self._web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    
    async def get_service_status(self) -> Dict:
        """Get DEX service status."""
        return {
            "enabled": self._enabled,
            "is_ready": self.is_enabled(),
            "conversion_wallet": self._conversion_wallet_address[:10] + "..." if self._conversion_wallet_address else None,
            "settlement_wallet": self._settlement_wallet_address[:10] + "..." if self._settlement_wallet_address else None,
            "config": {
                "max_slippage_pct": self._max_slippage_pct,
                "min_liquidity_depth_eur": self._min_liquidity_depth_eur,
                "max_price_impact_pct": self._max_price_impact_pct,
                "daily_cap_eur": self._daily_cap_eur,
                "daily_volume_eur": self._daily_volume_eur
            },
            "whitelisted_accounts": len(self._whitelisted_accounts),
            "web3_connected": self._web3 is not None
        }
    
    async def enable_live_mode(self, user_id: str = None):
        """Enable live DEX execution (admin only)."""
        await self.config_collection.update_one(
            {"config_type": "dex"},
            {
                "$set": {
                    "enabled": True,
                    "enabled_at": datetime.now(timezone.utc).isoformat(),
                    "enabled_by": user_id
                }
            }
        )
        self._enabled = True
        logger.info(f"[DEX] LIVE MODE ENABLED by {user_id}")
    
    async def disable_live_mode(self, reason: str = None):
        """Disable live DEX execution (emergency stop)."""
        await self.config_collection.update_one(
            {"config_type": "dex"},
            {
                "$set": {
                    "enabled": False,
                    "disabled_at": datetime.now(timezone.utc).isoformat(),
                    "disabled_reason": reason
                }
            }
        )
        self._enabled = False
        logger.warning(f"[DEX] LIVE MODE DISABLED: {reason}")
    
    async def add_to_whitelist(self, user_id: str):
        """Add user to DEX whitelist."""
        if user_id not in self._whitelisted_accounts:
            self._whitelisted_accounts.append(user_id)
            await self.config_collection.update_one(
                {"config_type": "dex"},
                {"$addToSet": {"whitelisted_accounts": user_id}}
            )
            logger.info(f"[DEX] User {user_id} added to whitelist")


# Global instance
_dex_service: Optional[DEXService] = None


def get_dex_service() -> Optional[DEXService]:
    return _dex_service


def set_dex_service(service: DEXService):
    global _dex_service
    _dex_service = service

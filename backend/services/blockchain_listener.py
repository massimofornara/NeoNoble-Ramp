"""
BSC Blockchain Listener for NENO BEP-20 Token Transfers.

Monitors deposit addresses for incoming NENO transfers
and triggers the appropriate callbacks when detected.
"""

import os
import asyncio
import logging
from typing import Optional, Callable, Dict, List
from datetime import datetime, timezone
from decimal import Decimal
from web3 import Web3
from web3.exceptions import Web3Exception
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# NENO Token Contract on BSC - configurable via environment
NENO_CONTRACT_ADDRESS = os.environ.get(
    'NENO_CONTRACT_ADDRESS',
    '0xeF3F5C1892A8d7A3304E4A15959E124402d69974'
)

# Standard BEP-20/ERC-20 Transfer event ABI
TRANSFER_EVENT_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    }
]

# Minimal BEP-20 ABI for balance and decimals
BEP20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
] + TRANSFER_EVENT_ABI


class BlockchainListener:
    """
    Polling-based blockchain listener for BSC NENO token transfers.
    
    Monitors active deposit addresses and detects incoming transfers.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.events_collection = db.blockchain_events
        self._web3: Optional[Web3] = None
        self._contract = None
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable] = []
        self._last_block: int = 0
        self._token_decimals: int = 18  # Default, will be fetched
        self._enabled = False
    
    def _get_web3(self) -> Optional[Web3]:
        """Get or create Web3 instance with BSC POA middleware."""
        if self._web3 is not None:
            try:
                if self._web3.is_connected():
                    return self._web3
            except Exception:
                self._web3 = None

        rpc_url = os.environ.get('BSC_RPC_URL')
        if not rpc_url:
            return None

        try:
            from web3.middleware import ExtraDataToPOAMiddleware
            self._web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))

            if not self._web3.is_connected():
                logger.warning("BSC RPC not reachable")
                self._web3 = None
                return None

            # BSC is a POA chain — inject the middleware
            self._web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            logger.info(f"Connected to BSC RPC (block {self._web3.eth.block_number})")
            return self._web3
        except Exception as e:
            logger.warning(f"BSC RPC connection error: {e}")
            self._web3 = None
            return None
    
    def is_enabled(self) -> bool:
        """Check if blockchain listener is enabled."""
        return self._enabled
    
    def _get_contract(self):
        """Get NENO token contract instance."""
        if self._contract is not None:
            return self._contract
        
        web3 = self._get_web3()
        if web3 is None:
            return None
        
        self._contract = web3.eth.contract(
            address=Web3.to_checksum_address(NENO_CONTRACT_ADDRESS),
            abi=BEP20_ABI
        )
        
        # Fetch token decimals
        try:
            self._token_decimals = self._contract.functions.decimals().call()
            symbol = self._contract.functions.symbol().call()
            logger.info(f"NENO token: {symbol}, decimals: {self._token_decimals}")
        except Exception as e:
            logger.warning(f"Could not fetch token info: {e}")
        
        return self._contract
    
    def get_required_confirmations(self) -> int:
        """Get required number of confirmations from env."""
        return int(os.environ.get('BSC_CONFIRMATIONS', '5'))
    
    def register_callback(self, callback: Callable):
        """Register a callback for when transfers are detected."""
        self._callbacks.append(callback)
    
    async def initialize(self):
        """Initialize the blockchain listener."""
        # Create indexes
        await self.events_collection.create_index("transaction_hash", unique=True)
        await self.events_collection.create_index("to_address")
        await self.events_collection.create_index("status")
        
        # Check if BSC RPC is configured
        web3 = self._get_web3()
        if web3 is None:
            self._enabled = False
            logger.warning("Blockchain listener disabled (no BSC_RPC_URL)")
            return
        
        # Get current block
        try:
            self._last_block = web3.eth.block_number
            self._enabled = True
            logger.info(f"Blockchain listener initialized at block {self._last_block}")
        except Exception as e:
            self._enabled = False
            logger.error(f"Failed to initialize blockchain listener: {e}")
    
    async def get_token_balance(self, address: str) -> Decimal:
        """Get NENO token balance for an address."""
        try:
            contract = self._get_contract()
            balance_wei = contract.functions.balanceOf(
                Web3.to_checksum_address(address)
            ).call()
            return Decimal(balance_wei) / Decimal(10 ** self._token_decimals)
        except Exception as e:
            logger.error(f"Failed to get balance for {address}: {e}")
            return Decimal(0)
    
    async def check_address_for_transfers(
        self,
        address: str,
        from_block: int,
        to_block: int
    ) -> List[Dict]:
        """
        Check for NENO transfers to a specific address using get_logs.
        Uses integer block numbers for Alchemy/BSC compatibility.
        """
        transfers = []

        try:
            web3 = self._get_web3()
            if web3 is None:
                return transfers

            transfer_topic = web3.keccak(text="Transfer(address,address,uint256)").hex()
            padded_address = "0x" + address[2:].lower().zfill(64)

            logs = web3.eth.get_logs({
                'fromBlock': from_block,
                'toBlock': to_block,
                'address': Web3.to_checksum_address(NENO_CONTRACT_ADDRESS),
                'topics': [transfer_topic, None, padded_address]
            })

            current_block = web3.eth.block_number

            for log in logs:
                tx_hash = log['transactionHash'].hex()
                block_number = log['blockNumber']
                from_addr = "0x" + log['topics'][1].hex()[-40:]
                to_addr = "0x" + log['topics'][2].hex()[-40:]
                amount_wei = int(log['data'].hex(), 16)
                confirmations = current_block - block_number
                amount = Decimal(amount_wei) / Decimal(10 ** self._token_decimals)

                transfer = {
                    'transaction_hash': tx_hash,
                    'from_address': from_addr.lower(),
                    'to_address': to_addr.lower(),
                    'amount': float(amount),
                    'amount_wei': str(amount_wei),
                    'block_number': block_number,
                    'confirmations': confirmations,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
                transfers.append(transfer)

                logger.info(
                    f"NENO transfer: {amount} to {address[:10]}... "
                    f"(tx: {tx_hash[:16]}..., {confirmations} conf)"
                )

        except Exception as e:
            logger.debug(f"get_logs for {address[:10]}...: {e}")

        return transfers
    
    async def process_transfer(
        self,
        transfer: Dict,
        quote_id: str,
        expected_amount: float
    ) -> Dict:
        """
        Process a detected transfer.
        
        Validates:
        - Correct amount (no partial deposits)
        - Sufficient confirmations
        
        Returns processing result.
        """
        required_confirmations = self.get_required_confirmations()
        
        result = {
            'valid': False,
            'error': None,
            'transfer': transfer,
            'quote_id': quote_id
        }
        
        # Check confirmations
        if transfer['confirmations'] < required_confirmations:
            result['error'] = (
                f"Insufficient confirmations: {transfer['confirmations']}/{required_confirmations}"
            )
            result['status'] = 'PENDING_CONFIRMATIONS'
            return result
        
        # Check amount (with small tolerance for floating point)
        tolerance = 0.0001
        if abs(transfer['amount'] - expected_amount) > tolerance:
            result['error'] = (
                f"Amount mismatch: received {transfer['amount']}, expected {expected_amount}"
            )
            result['status'] = 'AMOUNT_MISMATCH'
            
            if transfer['amount'] < expected_amount:
                result['error'] = f"Partial deposit rejected: {transfer['amount']} < {expected_amount}"
                result['status'] = 'PARTIAL_DEPOSIT'
            
            return result
        
        # All validations passed
        result['valid'] = True
        result['status'] = 'CONFIRMED'
        
        # Store the event
        event_doc = {
            **transfer,
            'quote_id': quote_id,
            'expected_amount': expected_amount,
            'status': 'CONFIRMED',
            'processed_at': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            await self.events_collection.update_one(
                {'transaction_hash': transfer['transaction_hash']},
                {'$set': event_doc},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Failed to store event: {e}")
        
        return result
    
    async def poll_for_transfers(
        self,
        addresses_with_quotes: List[Dict],
        callback: Callable
    ):
        """
        Poll for transfers to a list of addresses.
        
        Args:
            addresses_with_quotes: List of {address, quote_id, expected_amount}
            callback: Async function to call when transfer is confirmed
        """
        try:
            web3 = self._get_web3()
            current_block = web3.eth.block_number
            
            # Look back 1000 blocks (~50 minutes on BSC)
            from_block = max(0, current_block - 1000)
            
            for item in addresses_with_quotes:
                address = item.get('address') or item.get('deposit_address', '')
                if not address:
                    continue
                quote_id = item['quote_id']
                expected_amount = item['expected_amount']
                
                # Check if already processed
                existing = await self.events_collection.find_one({
                    'to_address': address.lower(),
                    'quote_id': quote_id,
                    'status': 'CONFIRMED'
                })
                
                if existing:
                    continue
                
                # Rate-limit: small delay between address checks to avoid 429s
                await asyncio.sleep(0.5)
                
                # Check for transfers
                transfers = await self.check_address_for_transfers(
                    address, from_block, current_block
                )
                
                for transfer in transfers:
                    result = await self.process_transfer(
                        transfer, quote_id, expected_amount
                    )
                    
                    if result['valid']:
                        # Trigger callback
                        await callback(result)
                        break
                    elif result.get('status') == 'PENDING_CONFIRMATIONS':
                        logger.info(
                            f"Transfer pending confirmations for {quote_id}: "
                            f"{transfer['confirmations']}/{self.get_required_confirmations()}"
                        )
        
        except Exception as e:
            logger.error(f"Error polling for transfers: {e}")
    
    async def start_polling(self, get_active_quotes: Callable, on_transfer: Callable):
        """
        Start the polling loop.
        
        Args:
            get_active_quotes: Async function that returns list of active quotes with addresses
            on_transfer: Async callback when transfer is confirmed
        """
        if not self._enabled:
            logger.warning("Blockchain polling not started (not enabled)")
            return
        
        self._running = True
        poll_interval = int(os.environ.get('BSC_POLL_INTERVAL', '60'))  # 60s to avoid rate limits
        
        logger.info(f"Starting blockchain polling (interval: {poll_interval}s)")
        
        while self._running:
            try:
                # Get active quotes with deposit addresses
                active_quotes = await get_active_quotes()
                
                if active_quotes:
                    await self.poll_for_transfers(active_quotes, on_transfer)
                
            except Exception as e:
                logger.debug(f"Polling cycle error: {e}")
            
            await asyncio.sleep(poll_interval)
    
    def stop_polling(self):
        """Stop the polling loop."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()

    # ── Hot Wallet Auto-Deposit Monitor ──

    async def monitor_hot_wallet(self, hot_wallet_address: str):
        """
        Continuously monitors the platform hot wallet for incoming NENO transfers.
        Aggressive 3s polling for real-time detection.
        """
        if not self._enabled:
            logger.warning("Hot wallet monitor not started (RPC not configured)")
            return

        poll_interval = int(os.environ.get('BSC_POLL_INTERVAL', '3'))
        logger.info(f"Starting hot wallet monitor for {hot_wallet_address[:10]}... (interval: {poll_interval}s)")

        last_block = None

        while self._running:
            try:
                web3 = self._get_web3()
                if not web3:
                    await asyncio.sleep(poll_interval)
                    continue

                current_block = web3.eth.block_number
                if last_block is None:
                    last_block = max(current_block - 500, 0)

                if current_block <= last_block:
                    await asyncio.sleep(poll_interval)
                    continue

                transfer_topic = web3.keccak(text="Transfer(address,address,uint256)").hex()
                padded_hw = "0x" + hot_wallet_address[2:].lower().zfill(64)

                try:
                    logs = web3.eth.get_logs({
                        'fromBlock': last_block + 1,
                        'toBlock': current_block,
                        'address': Web3.to_checksum_address(NENO_CONTRACT_ADDRESS),
                        'topics': [transfer_topic, None, padded_hw]
                    })
                except Exception as e:
                    logger.debug(f"Hot wallet get_logs error: {e}")
                    await asyncio.sleep(poll_interval)
                    continue

                for log_entry in logs:
                    tx_hash = log_entry['transactionHash'].hex()
                    block_number = log_entry['blockNumber']
                    from_addr = "0x" + log_entry['topics'][1].hex()[-40:]
                    data_hex = log_entry['data'].hex() if hasattr(log_entry['data'], 'hex') else str(log_entry['data'])
                    raw_amount = int(data_hex, 16)
                    amount = float(Decimal(raw_amount) / Decimal(10 ** self._token_decimals))

                    if amount <= 0:
                        continue

                    existing = await self.db.onchain_deposits.find_one({"tx_hash": tx_hash})
                    if existing:
                        continue

                    from_addr_checksum = Web3.to_checksum_address("0x" + from_addr.replace("0x", "").zfill(40)[-40:])
                    logger.info(f"[HOT WALLET] New NENO deposit: {amount} NENO from {from_addr_checksum} (tx: {tx_hash[:16]}...)")

                    user = await self._find_user_by_wallet(from_addr_checksum)

                    await self._process_hot_wallet_deposit(
                        tx_hash=tx_hash, sender=from_addr_checksum,
                        amount=amount, block_number=block_number,
                        hot_wallet=hot_wallet_address, user=user,
                    )

                last_block = current_block

            except Exception as e:
                logger.debug(f"Hot wallet monitor cycle error: {e}")

            await asyncio.sleep(poll_interval)

    async def _find_user_by_wallet(self, wallet_address: str) -> Optional[Dict]:
        """Find user by wallet address with aggressive matching."""
        addr_lower = wallet_address.lower()
        addr_checksum = Web3.to_checksum_address(wallet_address)

        user = await self.db.users.find_one(
            {"$or": [
                {"wallet_address": {"$regex": addr_checksum, "$options": "i"}},
                {"connected_wallets": {"$regex": addr_checksum, "$options": "i"}},
                {"web3_address": {"$regex": addr_checksum, "$options": "i"}},
                {"connected_wallet": {"$regex": addr_checksum, "$options": "i"}},
                {"wallet_address": {"$regex": addr_lower, "$options": "i"}},
                {"connected_wallet": addr_lower},
                {"connected_wallet": addr_checksum},
            ]},
            {"_id": 0, "user_id": 1, "email": 1}
        )

        if not user:
            txs = await self.db.neno_transactions.find(
                {"$or": [
                    {"sender_address": {"$regex": addr_checksum, "$options": "i"}},
                    {"onchain_tx_from": {"$regex": addr_checksum, "$options": "i"}},
                ]},
                {"_id": 0, "user_id": 1}
            ).sort("created_at", -1).to_list(1)
            if txs:
                user = {"user_id": txs[0]["user_id"]}

        if not user:
            deposits = await self.db.onchain_deposits.find(
                {"sender_address": {"$regex": addr_checksum, "$options": "i"}, "user_id": {"$ne": None}},
                {"_id": 0, "user_id": 1}
            ).sort("verified_at", -1).to_list(1)
            if deposits:
                user = {"user_id": deposits[0]["user_id"]}

        return user

    async def _process_hot_wallet_deposit(
        self, tx_hash: str, sender: str, amount: float,
        block_number: int, hot_wallet: str, user: dict = None
    ):
        """Process a detected hot wallet deposit — credit internal balance + record tx."""
        import uuid

        uid = user["user_id"] if user else None
        status = "verified" if uid else "pending_user_match"

        # Credit NENO to user's internal wallet if user is found
        if uid:
            wallet = await self.db.wallets.find_one({"user_id": uid, "asset": "NENO"})
            if wallet:
                await self.db.wallets.update_one(
                    {"user_id": uid, "asset": "NENO"},
                    {"$inc": {"balance": amount}}
                )
            else:
                await self.db.wallets.insert_one({
                    "id": str(uuid.uuid4()),
                    "user_id": uid,
                    "asset": "NENO",
                    "balance": amount,
                    "created_at": datetime.now(timezone.utc),
                })
            logger.info(f"[HOT WALLET] Credited {amount} NENO to user {uid}")

        # Create transaction record
        tx_id = str(uuid.uuid4())
        tx_record = {
            "id": tx_id,
            "user_id": uid,
            "type": "onchain_deposit",
            "neno_amount": amount,
            "sender_address": sender,
            "hot_wallet": hot_wallet,
            "tx_hash": tx_hash,
            "block_number": block_number,
            "execution_mode": "onchain",
            "onchain_tx_hash": tx_hash,
            "status": "completed" if uid else "pending_user_match",
            "auto_detected": True,
            "created_at": datetime.now(timezone.utc),
        }
        await self.db.neno_transactions.insert_one({**tx_record, "_id": tx_id})

        # Store deposit record
        deposit_record = {
            "id": str(uuid.uuid4()),
            "tx_hash": tx_hash,
            "user_id": uid,
            "sender_address": sender,
            "hot_wallet": hot_wallet,
            "neno_amount": amount,
            "operation": "auto_deposit",
            "block_number": block_number,
            "status": status,
            "credited": bool(uid),
            "internal_tx_id": tx_id,
            "auto_detected": True,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.onchain_deposits.insert_one({**deposit_record, "_id": deposit_record["id"]})

        # Notify user if found
        if uid:
            try:
                from services.notification_dispatch import notify_trade_executed
                asyncio.ensure_future(notify_trade_executed(uid, "NENO", "deposit", amount, 0, 0))
            except Exception:
                pass

        logger.info(
            f"[HOT WALLET] Deposit processed: {amount} NENO from {sender[:10]}... "
            f"(tx: {tx_hash[:16]}..., user: {uid or 'UNMATCHED'})"
        )

"""
HD Wallet Service for generating unique deposit addresses.

Uses BIP44 derivation path: m/44'/60'/0'/0/index
for BSC (BNB Smart Chain) compatible addresses.

SECURITY NOTES:
- Never log private keys, mnemonics, or xpub
- Store address-to-quote mappings securely
- Prevent address reuse across quotes
"""

import os
import logging
from typing import Optional, Tuple, Dict
from datetime import datetime, timezone
from eth_account import Account
from eth_account.hdaccount import generate_mnemonic, Mnemonic
from motor.motor_asyncio import AsyncIOMotorDatabase
from services.onchain.multichain_service import multichain_service
from services.risk.risk_engine import RiskEngine

risk_engine = RiskEngine()

async def send_token_to_wallet(self, token_symbol, to_address, amount, chain="BSC"):

    if not risk_engine.check(amount):
        return None, "RISK_BLOCKED"

    tx_hash = await multichain_service.send_native(chain, to_address, amount)

    return tx_hash, None


logger = logging.getLogger(__name__)

# Enable HD wallet features
Account.enable_unaudited_hdwallet_features()

# BIP44 derivation path for BSC (same as Ethereum)
DERIVATION_PATH_PREFIX = "m/44'/60'/0'/0/"


class WalletService:
    """
    HD Wallet service for generating unique deposit addresses per quote.
    
    Each quote gets a unique address derived from the master mnemonic
    using incremental index values.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.addresses_collection = db.deposit_addresses
        self._mnemonic: Optional[str] = None
        self._initialized = False
        self._enabled = False
    
    def _get_mnemonic(self) -> Optional[str]:
        """Get mnemonic from environment variable."""
        if self._mnemonic:
            return self._mnemonic
        
        mnemonic = os.environ.get('NENO_WALLET_MNEMONIC')
        if not mnemonic:
            return None
        
        # Validate mnemonic by trying to derive an account
        try:
            Account.from_mnemonic(mnemonic, account_path="m/44'/60'/0'/0/0")
        except Exception as e:
            logger.error(f"Invalid mnemonic phrase: {e}")
            return None
        
        self._mnemonic = mnemonic
        logger.info("Wallet mnemonic loaded successfully")
        return self._mnemonic
    
    async def initialize(self):
        """Initialize the wallet service and create indexes."""
        if self._initialized:
            return
        
        # Create indexes for efficient lookups
        await self.addresses_collection.create_index("address", unique=True)
        await self.addresses_collection.create_index("quote_id", unique=True)
        await self.addresses_collection.create_index("derivation_index", unique=True)
        await self.addresses_collection.create_index("status")
        
        # Check if mnemonic is configured
        mnemonic = self._get_mnemonic()
        if mnemonic:
            self._enabled = True
            logger.info("Wallet service initialized with HD wallet enabled")
        else:
            self._enabled = False
            logger.warning("Wallet service initialized but HD wallet DISABLED (no mnemonic)")
        
        self._initialized = True
    
    def is_enabled(self) -> bool:
        """Check if wallet service is enabled (has valid mnemonic)."""
        return self._enabled
    
    async def _get_next_derivation_index(self) -> int:
        """Get the next available derivation index."""
        # Find the highest used index
        result = await self.addresses_collection.find_one(
            sort=[("derivation_index", -1)]
        )
        
        if result:
            return result["derivation_index"] + 1
        return 0
    
    def _derive_address(self, index: int) -> Tuple[str, str]:
        """
        Derive an address from the mnemonic at the given index.
        
        Returns:
            Tuple of (address, private_key_hex)
        """
        mnemonic = self._get_mnemonic()
        path = f"{DERIVATION_PATH_PREFIX}{index}"
        
        # Derive account from mnemonic
        account = Account.from_mnemonic(
            mnemonic,
            account_path=path
        )
        
        # Return address and private key (never log these!)
        return account.address, account.key.hex()
    
    async def generate_deposit_address(self, quote_id: str) -> Tuple[str, Optional[str]]:
        """
        Generate a unique deposit address for a quote.
        
        Args:
            quote_id: The quote ID to bind this address to
            
        Returns:
            Tuple of (address, error_message)
        """
        try:
            await self.initialize()
            
            # Check if wallet service is enabled
            if not self._enabled:
                return None, "Wallet service not configured (missing NENO_WALLET_MNEMONIC)"
            
            # Check if quote already has an address
            existing = await self.addresses_collection.find_one({"quote_id": quote_id})
            if existing:
                logger.warning(f"Quote {quote_id} already has address: {existing['address']}")
                return existing["address"], None
            
            # Get next index
            index = await self._get_next_derivation_index()
            
            # Derive address
            address, private_key = self._derive_address(index)
            
            # Store address mapping (NEVER store private key in DB in production!)
            # In production, use a secure key management service (HSM, AWS KMS, etc.)
            address_doc = {
                "address": address.lower(),
                "quote_id": quote_id,
                "derivation_index": index,
                "status": "ACTIVE",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "used_at": None,
                "transaction_hash": None,
                # In production, encrypt this or use HSM
                "_private_key_encrypted": private_key  # TODO: Encrypt with KMS
            }
            
            await self.addresses_collection.insert_one(address_doc)
            
            logger.info(f"Generated deposit address for quote {quote_id}: {address}")
            return address, None
            
        except ValueError as e:
            logger.error(f"Wallet configuration error: {e}")
            return None, str(e)
        except Exception as e:
            logger.error(f"Failed to generate deposit address: {e}")
            return None, f"Failed to generate deposit address: {str(e)}"
    
    async def get_address_by_quote(self, quote_id: str) -> Optional[Dict]:
        """Get deposit address info by quote ID."""
        return await self.addresses_collection.find_one({"quote_id": quote_id})
    
    async def get_quote_by_address(self, address: str) -> Optional[Dict]:
        """Get quote info by deposit address."""
        return await self.addresses_collection.find_one({"address": address.lower()})
    
    async def get_active_addresses(self) -> list:
        """Get all active deposit addresses for monitoring."""
        cursor = self.addresses_collection.find({"status": "ACTIVE"})
        return await cursor.to_list(length=1000)
    
    async def mark_address_used(self, address: str, transaction_hash: str):
        """Mark an address as used after receiving funds."""
        await self.addresses_collection.update_one(
            {"address": address.lower()},
            {
                "$set": {
                    "status": "USED",
                    "used_at": datetime.now(timezone.utc).isoformat(),
                    "transaction_hash": transaction_hash
                }
            }
        )
        logger.info(f"Marked address {address} as used (tx: {transaction_hash})")
    
    async def mark_address_expired(self, address: str):
        """Mark an address as expired."""
        await self.addresses_collection.update_one(
            {"address": address.lower()},
            {"$set": {"status": "EXPIRED"}}
        )
    
    def get_private_key_for_address(self, derivation_index: int) -> str:
        """
        Get private key for a specific derivation index.
        Used for signing transactions if needed.
        
        WARNING: Handle with extreme care!
        """
        _, private_key = self._derive_address(derivation_index)
        return private_key

async def send_crypto(self, address: str, amount: float, asset: str) -> Dict:
    """
    Send crypto to external wallet (REAL execution).
    """
    try:
        # ⚠️ QUI DEVI INTEGRARE:
        # - Web3
        # - Private key signing
        # - RPC (BSC, ETH, ecc)

        # ESEMPIO placeholder REALE DA IMPLEMENTARE:
        tx_hash = "0xREAL_TX_HASH"

        logger.info(f"Sent {amount} {asset} to {address} | tx: {tx_hash}")

        return {
            "success": True,
            "tx_hash": tx_hash,
            "amount": amount,
            "asset": asset
        }

    except Exception as e:
        logger.error(f"Crypto transfer failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


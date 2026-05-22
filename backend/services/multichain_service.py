"""
Multi-Chain Wallet Service.

Real on-chain balance synchronization for:
- Ethereum (ETH + ERC-20 tokens)
- BNB Smart Chain (BNB + BEP-20 tokens)
- Polygon (MATIC + ERC-20 tokens)

Pipeline: Wallet Address → Chain Selection → Blockchain Query → Balance & Token Update
"""

import os
import logging
import asyncio
from typing import Optional
from datetime import datetime, timezone
from web3 import Web3
from database.mongodb import get_database

logger = logging.getLogger(__name__)

# Chain configurations
CHAINS = {
    "ethereum": {
        "chain_id": 1,
        "name": "Ethereum",
        "symbol": "ETH",
        "rpc_url": "https://eth.llamarpc.com",
        "explorer": "https://etherscan.io",
        "decimals": 18,
        "icon": "ethereum",
    },
    "bsc": {
        "chain_id": 56,
        "name": "BNB Smart Chain",
        "symbol": "BNB",
        "rpc_url": os.environ.get("BSC_RPC_URL", "https://bsc-dataseed1.binance.org"),
        "explorer": "https://bscscan.com",
        "decimals": 18,
        "icon": "bnb",
    },
    "polygon": {
        "chain_id": 137,
        "name": "Polygon",
        "symbol": "MATIC",
        "rpc_url": "https://polygon.llamarpc.com",
        "explorer": "https://polygonscan.com",
        "decimals": 18,
        "icon": "polygon",
    },
}

# Well-known token addresses per chain
KNOWN_TOKENS = {
    "ethereum": {
        "USDT": {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
        "USDC": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
        "LINK": {"address": "0x514910771AF9Ca656af840dff83E8264EcF986CA", "decimals": 18},
    },
    "bsc": {
        "NENO": {"address": os.environ.get("NENO_CONTRACT_ADDRESS", "0xeF3F5C1892A8d7A3304E4A15959E124402d69974"), "decimals": 18},
        "USDT": {"address": "0x55d398326f99059fF775485246999027B3197955", "decimals": 18},
        "BUSD": {"address": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56", "decimals": 18},
    },
    "polygon": {
        "USDT": {"address": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F", "decimals": 6},
        "USDC": {"address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "decimals": 6},
    },
}

ERC20_BALANCE_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
]


def _get_web3(chain_key: str) -> Optional[Web3]:
    cfg = CHAINS.get(chain_key)
    if not cfg:
        return None
    try:
        w3 = Web3(Web3.HTTPProvider(cfg["rpc_url"], request_kwargs={"timeout": 10}))
        return w3 if w3.is_connected() else None
    except Exception as e:
        logger.warning(f"Failed to connect to {chain_key}: {e}")
        return None


async def get_native_balance(chain_key: str, address: str) -> dict:
    """Get native token balance (ETH/BNB/MATIC) for an address."""
    cfg = CHAINS.get(chain_key)
    if not cfg:
        return {"error": f"Unsupported chain: {chain_key}"}

    try:
        w3 = _get_web3(chain_key)
        if not w3:
            return {"balance": 0, "symbol": cfg["symbol"], "chain": chain_key, "synced": False}

        checksum = Web3.to_checksum_address(address)
        balance_wei = await asyncio.to_thread(w3.eth.get_balance, checksum)
        balance = float(Web3.from_wei(balance_wei, "ether"))

        return {
            "balance": round(balance, 8),
            "symbol": cfg["symbol"],
            "chain": chain_key,
            "chain_name": cfg["name"],
            "chain_id": cfg["chain_id"],
            "address": address,
            "synced": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting balance on {chain_key}: {e}")
        return {"balance": 0, "symbol": cfg["symbol"], "chain": chain_key, "synced": False, "error": str(e)}


async def get_token_balance(chain_key: str, address: str, token_address: str, decimals: int = 18) -> dict:
    """Get ERC-20/BEP-20 token balance."""
    try:
        w3 = _get_web3(chain_key)
        if not w3:
            return {"balance": 0, "synced": False}

        checksum_addr = Web3.to_checksum_address(address)
        checksum_token = Web3.to_checksum_address(token_address)
        contract = w3.eth.contract(address=checksum_token, abi=ERC20_BALANCE_ABI)

        raw_balance = await asyncio.to_thread(contract.functions.balanceOf(checksum_addr).call)
        balance = raw_balance / (10 ** decimals)

        try:
            symbol = await asyncio.to_thread(contract.functions.symbol().call)
        except Exception:
            symbol = "UNKNOWN"

        return {
            "balance": round(balance, 8),
            "symbol": symbol,
            "token_address": token_address,
            "chain": chain_key,
            "synced": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error getting token balance on {chain_key}: {e}")
        return {"balance": 0, "synced": False, "error": str(e)}


async def get_all_balances(chain_key: str, address: str) -> dict:
    """Get all balances (native + known tokens) for an address on a chain."""
    cfg = CHAINS.get(chain_key)
    if not cfg:
        return {"error": f"Unsupported chain: {chain_key}"}

    native = await get_native_balance(chain_key, address)
    tokens = []
    known = KNOWN_TOKENS.get(chain_key, {})

    for token_sym, token_info in known.items():
        tb = await get_token_balance(chain_key, address, token_info["address"], token_info["decimals"])
        tb["symbol"] = token_sym
        tokens.append(tb)

    return {
        "chain": chain_key,
        "chain_name": cfg["name"],
        "chain_id": cfg["chain_id"],
        "address": address,
        "native": native,
        "tokens": tokens,
        "synced": native.get("synced", False),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def sync_wallet_onchain(user_id: str, address: str, chain_key: str) -> dict:
    """Sync a user's wallet with on-chain data and store in DB."""
    db = get_database()
    balances = await get_all_balances(chain_key, address)

    await db.onchain_wallets.update_one(
        {"user_id": user_id, "chain": chain_key},
        {
            "$set": {
                "address": address,
                "chain": chain_key,
                "chain_name": balances.get("chain_name"),
                "chain_id": balances.get("chain_id"),
                "native_balance": balances.get("native", {}).get("balance", 0),
                "native_symbol": balances.get("native", {}).get("symbol"),
                "tokens": balances.get("tokens", []),
                "synced": balances.get("synced", False),
                "last_sync": datetime.now(timezone.utc),
            },
            "$setOnInsert": {"user_id": user_id, "created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )

    return balances


async def get_supported_chains() -> list:
    """Get all supported chains with connection status."""
    result = []
    for key, cfg in CHAINS.items():
        connected = False
        try:
            w3 = _get_web3(key)
            connected = w3 is not None
        except Exception:
            pass

        result.append({
            "key": key,
            "name": cfg["name"],
            "symbol": cfg["symbol"],
            "chain_id": cfg["chain_id"],
            "explorer": cfg["explorer"],
            "connected": connected,
        })
    return result


async def get_recent_transactions(chain_key: str, address: str, limit: int = 20) -> list:
    """Get recent transactions for an address (from DB cache)."""
    db = get_database()
    txs = await db.onchain_transactions.find(
        {"chain": chain_key, "$or": [{"from": address.lower()}, {"to": address.lower()}]},
        {"_id": 0},
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return txs

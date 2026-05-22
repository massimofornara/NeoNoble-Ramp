"""
Multi-Chain Wallet API Routes.

On-chain wallet synchronization for:
- Real-time balance reading across chains
- Multi-chain support (ETH, BSC, Polygon)
- Token discovery and tracking
- Transaction history per chain
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid

from routes.auth import get_current_user
from services.multichain_service import (
    get_all_balances,
    sync_wallet_onchain,
    get_supported_chains,
    get_recent_transactions,
    CHAINS,
)
from database.mongodb import get_database

router = APIRouter(prefix="/multichain", tags=["Multi-Chain Wallet"])


class LinkWalletRequest(BaseModel):
    address: str
    chain: str = Field(default="ethereum")


class SyncRequest(BaseModel):
    chain: str


@router.get("/chains")
async def list_supported_chains():
    """Get all supported blockchain networks."""
    chains = await get_supported_chains()
    return {"chains": chains, "total": len(chains)}


@router.post("/link")
async def link_wallet(request: LinkWalletRequest, current_user: dict = Depends(get_current_user)):
    """Link a wallet address and sync on-chain balances."""
    if request.chain not in CHAINS:
        raise HTTPException(status_code=400, detail=f"Chain non supportata: {request.chain}")

    if not request.address or len(request.address) != 42 or not request.address.startswith("0x"):
        raise HTTPException(status_code=400, detail="Indirizzo wallet non valido")

    db = get_database()
    await db.user_wallets.update_one(
        {"user_id": current_user["user_id"]},
        {
            "$addToSet": {"linked_addresses": {"address": request.address, "chain": request.chain}},
            "$setOnInsert": {"user_id": current_user["user_id"]},
        },
        upsert=True,
    )

    balances = await sync_wallet_onchain(current_user["user_id"], request.address, request.chain)
    return {"message": f"Wallet collegato su {CHAINS[request.chain]['name']}", "balances": balances}


@router.post("/sync")
async def sync_chain(request: SyncRequest, current_user: dict = Depends(get_current_user)):
    """Force sync wallet balances for a specific chain."""
    if request.chain not in CHAINS:
        raise HTTPException(status_code=400, detail=f"Chain non supportata: {request.chain}")

    db = get_database()
    user_wallet = await db.user_wallets.find_one({"user_id": current_user["user_id"]})
    if not user_wallet:
        raise HTTPException(status_code=404, detail="Nessun wallet collegato")

    linked = user_wallet.get("linked_addresses", [])
    chain_addresses = [la for la in linked if la.get("chain") == request.chain]
    if not chain_addresses:
        raise HTTPException(status_code=404, detail=f"Nessun wallet collegato per {request.chain}")

    results = []
    for la in chain_addresses:
        bal = await sync_wallet_onchain(current_user["user_id"], la["address"], request.chain)
        results.append(bal)

    return {"chain": request.chain, "synced_wallets": results}


@router.get("/balances")
async def get_multichain_balances(current_user: dict = Depends(get_current_user)):
    """Get all on-chain balances across all linked chains."""
    db = get_database()
    wallets = await db.onchain_wallets.find(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    ).to_list(20)

    for w in wallets:
        if "last_sync" in w and hasattr(w["last_sync"], "isoformat"):
            w["last_sync"] = w["last_sync"].isoformat()
        if "created_at" in w and hasattr(w["created_at"], "isoformat"):
            w["created_at"] = w["created_at"].isoformat()

    return {"wallets": wallets, "total_chains": len(wallets)}


@router.get("/balances/{chain}")
async def get_chain_balances(chain: str, current_user: dict = Depends(get_current_user)):
    """Get balances for a specific chain."""
    if chain not in CHAINS:
        raise HTTPException(status_code=400, detail=f"Chain non supportata: {chain}")

    db = get_database()
    wallet = await db.onchain_wallets.find_one(
        {"user_id": current_user["user_id"], "chain": chain}, {"_id": 0}
    )
    if not wallet:
        return {"chain": chain, "synced": False, "message": "Nessun wallet sincronizzato per questa chain"}

    if "last_sync" in wallet and hasattr(wallet["last_sync"], "isoformat"):
        wallet["last_sync"] = wallet["last_sync"].isoformat()
    if "created_at" in wallet and hasattr(wallet["created_at"], "isoformat"):
        wallet["created_at"] = wallet["created_at"].isoformat()

    return wallet


@router.get("/transactions/{chain}")
async def get_chain_transactions(
    chain: str,
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Get on-chain transactions for a chain."""
    db = get_database()
    user_wallet = await db.user_wallets.find_one({"user_id": current_user["user_id"]})
    if not user_wallet:
        return {"transactions": [], "total": 0}

    linked = user_wallet.get("linked_addresses", [])
    chain_addresses = [la["address"] for la in linked if la.get("chain") == chain]
    if not chain_addresses:
        return {"transactions": [], "total": 0}

    txs = await get_recent_transactions(chain, chain_addresses[0], limit)
    return {"transactions": txs, "total": len(txs), "chain": chain}


@router.get("/linked")
async def get_linked_wallets(current_user: dict = Depends(get_current_user)):
    """Get all linked wallet addresses."""
    db = get_database()
    user_wallet = await db.user_wallets.find_one(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    )
    if not user_wallet:
        return {"linked_addresses": [], "total": 0}
    return {"linked_addresses": user_wallet.get("linked_addresses", []), "total": len(user_wallet.get("linked_addresses", []))}


# -- Token Discovery --

@router.post("/discover-tokens")
async def discover_tokens(request: SyncRequest, current_user: dict = Depends(get_current_user)):
    """Auto-discover ERC-20/BEP-20 tokens on a linked wallet address."""
    if request.chain not in CHAINS:
        raise HTTPException(status_code=400, detail=f"Chain non supportata: {request.chain}")

    db = get_database()
    user_wallet = await db.user_wallets.find_one({"user_id": current_user["user_id"]})
    if not user_wallet:
        raise HTTPException(status_code=404, detail="Nessun wallet collegato")

    linked = user_wallet.get("linked_addresses", [])
    chain_addresses = [la for la in linked if la.get("chain") == request.chain]
    if not chain_addresses:
        raise HTTPException(status_code=404, detail=f"Nessun wallet per {request.chain}")

    address = chain_addresses[0]["address"]
    from services.multichain_service import KNOWN_TOKENS, get_token_balance

    discovered = []
    known = KNOWN_TOKENS.get(request.chain, {})
    for sym, info in known.items():
        tb = await get_token_balance(request.chain, address, info["address"], info["decimals"])
        tb["symbol"] = sym
        tb["token_address"] = info["address"]
        if tb.get("balance", 0) > 0:
            discovered.append(tb)

    # Also check for custom tokens the user has added
    custom_tokens = await db.custom_tokens.find(
        {"user_id": current_user["user_id"], "chain": request.chain}, {"_id": 0}
    ).to_list(50)
    for ct in custom_tokens:
        tb = await get_token_balance(request.chain, address, ct["address"], ct.get("decimals", 18))
        tb["symbol"] = ct.get("symbol", "UNKNOWN")
        tb["token_address"] = ct["address"]
        tb["custom"] = True
        discovered.append(tb)

    # Store discovered tokens
    await db.onchain_wallets.update_one(
        {"user_id": current_user["user_id"], "chain": request.chain},
        {"$set": {"tokens": discovered, "last_discovery": datetime.now(timezone.utc)}},
    )

    return {"chain": request.chain, "discovered_tokens": discovered, "total": len(discovered)}


class AddCustomTokenRequest(BaseModel):
    chain: str
    address: str
    symbol: str = ""
    decimals: int = 18


@router.post("/add-token")
async def add_custom_token(request: AddCustomTokenRequest, current_user: dict = Depends(get_current_user)):
    """Add a custom token to track on a chain."""
    if request.chain not in CHAINS:
        raise HTTPException(status_code=400, detail=f"Chain non supportata: {request.chain}")

    db = get_database()
    existing = await db.custom_tokens.find_one({
        "user_id": current_user["user_id"], "chain": request.chain,
        "address": request.address.lower()
    })
    if existing:
        return {"message": "Token gia' aggiunto"}

    # Try to get symbol from chain if not provided
    symbol = request.symbol
    if not symbol:
        from services.multichain_service import get_token_balance
        info = await get_token_balance(request.chain, "0x0000000000000000000000000000000000000000", request.address, request.decimals)
        symbol = info.get("symbol", "UNKNOWN")

    token = {
        "id": str(uuid.uuid4()),
        "user_id": current_user["user_id"],
        "chain": request.chain,
        "address": request.address.lower(),
        "symbol": symbol,
        "decimals": request.decimals,
        "created_at": datetime.now(timezone.utc),
    }
    await db.custom_tokens.insert_one({**token, "_id": token["id"]})
    token["created_at"] = token["created_at"].isoformat()
    return {"message": f"Token {symbol} aggiunto su {request.chain}", "token": token}


# -- Unified Wallet (Internal + External) --

@router.get("/unified-wallet")
async def get_unified_wallet(current_user: dict = Depends(get_current_user)):
    """Get unified view: internal platform wallet + on-chain wallets with same total value."""
    db = get_database()
    uid = current_user["user_id"]

    # Internal platform balances
    internal = await db.wallets.find({"user_id": uid}, {"_id": 0}).to_list(50)

    # On-chain balances
    onchain = await db.onchain_wallets.find({"user_id": uid}, {"_id": 0}).to_list(20)

    # Market prices for EUR conversion
    from routes.neno_exchange_routes import MARKET_PRICES_EUR, NENO_EUR_PRICE

    unified = {}
    total_eur = 0.0

    # Add internal balances
    for w in internal:
        asset = w["asset"]
        bal = w.get("balance", 0)
        if asset == "NENO":
            eur_val = bal * NENO_EUR_PRICE
        elif asset in MARKET_PRICES_EUR:
            eur_val = bal * MARKET_PRICES_EUR[asset]
        else:
            eur_val = bal
        unified[asset] = {
            "asset": asset,
            "internal_balance": round(bal, 8),
            "external_balance": 0.0,
            "total_balance": round(bal, 8),
            "eur_value": round(eur_val, 2),
            "source": "internal",
        }
        total_eur += eur_val

    # Add on-chain balances
    for oc in onchain:
        chain = oc.get("chain", "")
        native_sym = oc.get("native_symbol", "")
        native_bal = oc.get("native_balance", 0)

        if native_sym and native_bal > 0:
            eur_price = MARKET_PRICES_EUR.get(native_sym, 0)
            eur_val = native_bal * eur_price
            if native_sym in unified:
                unified[native_sym]["external_balance"] = round(unified[native_sym].get("external_balance", 0) + native_bal, 8)
                unified[native_sym]["total_balance"] = round(unified[native_sym]["internal_balance"] + unified[native_sym]["external_balance"], 8)
                unified[native_sym]["eur_value"] = round(unified[native_sym]["total_balance"] * eur_price, 2)
                unified[native_sym]["source"] = "both"
            else:
                unified[native_sym] = {
                    "asset": native_sym,
                    "internal_balance": 0.0,
                    "external_balance": round(native_bal, 8),
                    "total_balance": round(native_bal, 8),
                    "eur_value": round(eur_val, 2),
                    "chain": chain,
                    "source": "external",
                }
            total_eur += eur_val

        for tok in oc.get("tokens", []):
            sym = tok.get("symbol", "")
            bal = tok.get("balance", 0)
            if sym and bal > 0:
                eur_price = MARKET_PRICES_EUR.get(sym, 0)
                eur_val = bal * eur_price
                if sym in unified:
                    unified[sym]["external_balance"] = round(unified[sym].get("external_balance", 0) + bal, 8)
                    unified[sym]["total_balance"] = round(unified[sym]["internal_balance"] + unified[sym]["external_balance"], 8)
                    eur_price_total = MARKET_PRICES_EUR.get(sym, 0)
                    unified[sym]["eur_value"] = round(unified[sym]["total_balance"] * eur_price_total, 2)
                    unified[sym]["source"] = "both"
                else:
                    unified[sym] = {
                        "asset": sym,
                        "internal_balance": 0.0,
                        "external_balance": round(bal, 8),
                        "total_balance": round(bal, 8),
                        "eur_value": round(eur_val, 2),
                        "chain": chain,
                        "source": "external",
                    }
                total_eur += eur_val

    assets = sorted(unified.values(), key=lambda x: x["eur_value"], reverse=True)
    return {
        "assets": assets,
        "total_eur_value": round(total_eur, 2),
        "internal_count": len(internal),
        "external_chains": len(onchain),
    }

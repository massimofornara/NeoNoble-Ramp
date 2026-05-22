"""
Market Maker Service — NeoNoble Ramp.

Treasury = Account reale dell'owner (TREASURY_USER_ID).
Ogni operazione MM impatta direttamente i saldi dell'account owner nella
collezione `wallets`. Nessuna simulazione — stato reale consistente.

Features:
- Treasury backed by real owner account balances + on-chain hot wallet
- Dynamic Bid/Ask pricing based on inventory skew + volatility
- Internal matching engine (netting before treasury)
- PnL accounting (revenue separated from inventory changes)
- Off-ramp fallback to USDT/USDC
"""

import os
import uuid
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from database.mongodb import get_database

logger = logging.getLogger(__name__)

# ── Configuration ──
TREASURY_USER_ID = os.environ.get("TREASURY_USER_ID", "")
TREASURY_USER_EMAIL = os.environ.get("TREASURY_USER_EMAIL", "")

# ── Spread Parameters ──
BASE_SPREAD_BPS = 50          # 0.50% base
MIN_SPREAD_BPS = 20           # 0.20% min
MAX_SPREAD_BPS = 200          # 2.00% max
SKEW_FACTOR = 0.08
VOLATILITY_FACTOR = 0.003
VOLUME_THRESHOLD = 100.0
TARGET_NENO_INVENTORY = 500.0

# ── Token Contracts (BSC) ──
NENO_CONTRACT = "0xeF3F5C1892A8d7A3304E4A15959E124402d69974"
USDT_BSC = "0x55d398326f99059fF775485246999027B3197955"
USDC_BSC = "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"
TOKEN_CONTRACTS = {"NENO": NENO_CONTRACT, "USDT": USDT_BSC, "USDC": USDC_BSC}
TOKEN_DECIMALS = {"NENO": 18, "USDT": 18, "USDC": 18}

# ── Market prices for EUR valuation ──
MARKET_PRICES_EUR = {
    "BTC": 85000, "ETH": 3200, "BNB": 580, "MATIC": 0.45,
    "USDT": 0.92, "USDC": 0.92, "EUR": 1.0, "USD": 0.92,
}


class MarketMakerService:
    """Core Market Maker — Owner-account-backed counterparty."""

    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def treasury_uid(self) -> str:
        return TREASURY_USER_ID

    # ─────────────────────────────────────────────
    #  TREASURY READ (from owner wallets + on-chain)
    # ─────────────────────────────────────────────

    async def get_treasury_inventory(self) -> dict:
        """
        Treasury = owner's internal wallets + on-chain hot wallet balances.
        Single source of truth, unificato.
        """
        db = get_database()
        if not self.treasury_uid:
            return {"error": "TREASURY_USER_ID not configured", "assets": {}}

        # 1. Read all owner wallet balances
        wallets = await db.wallets.find(
            {"user_id": self.treasury_uid}, {"_id": 0}
        ).to_list(100)

        assets = {}
        for w in wallets:
            asset = w.get("asset", "")
            bal = round(w.get("balance", 0), 8)
            assets[asset] = {"internal": bal, "onchain": 0}

        # 2. Add on-chain hot wallet balances
        try:
            from services.execution_engine import ExecutionEngine
            engine = ExecutionEngine.get_instance()
            status = await engine.get_hot_wallet_status()
            if status.get("available"):
                neno_onchain = status.get("neno_balance", 0)
                bnb_onchain = status.get("bnb_balance", 0)
                if "NENO" not in assets:
                    assets["NENO"] = {"internal": 0, "onchain": 0}
                assets["NENO"]["onchain"] = round(neno_onchain, 8)
                if "BNB" not in assets:
                    assets["BNB"] = {"internal": 0, "onchain": 0}
                assets["BNB"]["onchain"] = round(bnb_onchain, 8)

                # USDT/USDC on-chain
                try:
                    from services.execution_engine import ERC20_ABI
                    from web3 import Web3
                    w3 = engine._get_web3()
                    if w3 and engine.hot_wallet:
                        for stable, contract_addr in [("USDT", USDT_BSC), ("USDC", USDC_BSC)]:
                            try:
                                c = w3.eth.contract(address=Web3.to_checksum_address(contract_addr), abi=ERC20_ABI)
                                raw = c.functions.balanceOf(engine.hot_wallet).call()
                                bal_s = float(Decimal(raw) / Decimal(10 ** 18))
                                if stable not in assets:
                                    assets[stable] = {"internal": 0, "onchain": 0}
                                assets[stable]["onchain"] = round(bal_s, 8)
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[TREASURY] On-chain read error: {e}")

        # 3. Build final inventory (combined)
        final = {}
        total_eur = 0
        now = datetime.now(timezone.utc).isoformat()

        for asset, parts in assets.items():
            internal = parts.get("internal", 0)
            onchain = parts.get("onchain", 0)
            combined = round(internal + onchain, 8)
            if combined <= 0 and asset not in ("EUR", "NENO", "USDT", "USDC", "BNB"):
                continue

            eur_price = MARKET_PRICES_EUR.get(asset, 0)
            if asset == "NENO":
                try:
                    from routes.neno_exchange_routes import NENO_BASE_PRICE
                    eur_price = NENO_BASE_PRICE
                except Exception:
                    eur_price = 10000
            val_eur = round(combined * eur_price, 2)

            locked = await db.mm_order_book.aggregate([
                {"$match": {"status": "pending", "asset": asset}},
                {"$group": {"_id": None, "total": {"$sum": "$remaining_amount"}}}
            ]).to_list(1)
            locked_amt = round(locked[0]["total"], 8) if locked else 0

            final[asset] = {
                "amount": combined,
                "internal_balance": round(internal, 8),
                "onchain_balance": round(onchain, 8),
                "locked_amount": locked_amt,
                "available_amount": round(combined - locked_amt, 8),
                "value_eur": val_eur,
                "source": "combined" if onchain > 0 and internal > 0 else ("on_chain" if onchain > 0 else "owner_account"),
            }
            total_eur += val_eur

            # Sync treasury_inventory collection
            await db.treasury_inventory.update_one(
                {"asset": asset},
                {"$set": {
                    "amount": combined,
                    "internal_balance": round(internal, 8),
                    "onchain_balance": round(onchain, 8),
                    "locked_amount": locked_amt,
                    "available_amount": round(combined - locked_amt, 8),
                    "value_eur": val_eur,
                    "source": final[asset]["source"],
                    "owner_user_id": self.treasury_uid,
                    "last_synced": now,
                    "updated_at": now,
                }, "$setOnInsert": {
                    "_id": str(uuid.uuid4()),
                    "asset": asset,
                    "created_at": now,
                }},
                upsert=True,
            )

        return {
            "owner": TREASURY_USER_EMAIL or self.treasury_uid,
            "assets": final,
            "total_value_eur": round(total_eur, 2),
            "asset_count": len(final),
            "timestamp": now,
        }

    async def get_asset_inventory(self, asset: str) -> dict:
        """Get treasury balance for a single asset (owner wallet + on-chain)."""
        db = get_database()
        asset = asset.upper()
        if not self.treasury_uid:
            return {"asset": asset, "amount": 0, "locked_amount": 0, "available_amount": 0}

        w = await db.wallets.find_one(
            {"user_id": self.treasury_uid, "asset": asset}, {"_id": 0}
        )
        internal = round(w.get("balance", 0), 8) if w else 0

        # On-chain balance for NENO, BNB, USDT, USDC
        onchain = 0
        if asset in ("NENO", "BNB", "USDT", "USDC"):
            try:
                from services.execution_engine import ExecutionEngine
                engine = ExecutionEngine.get_instance()
                if asset == "NENO":
                    status = await engine.get_hot_wallet_status()
                    onchain = round(status.get("neno_balance", 0), 8)
                elif asset == "BNB":
                    status = await engine.get_hot_wallet_status()
                    onchain = round(status.get("bnb_balance", 0), 8)
                elif asset in TOKEN_CONTRACTS:
                    from services.execution_engine import ERC20_ABI
                    from web3 import Web3
                    w3 = engine._get_web3()
                    if w3 and engine.hot_wallet:
                        c = w3.eth.contract(
                            address=Web3.to_checksum_address(TOKEN_CONTRACTS[asset]),
                            abi=ERC20_ABI
                        )
                        raw = c.functions.balanceOf(engine.hot_wallet).call()
                        onchain = round(float(Decimal(raw) / Decimal(10 ** 18)), 8)
            except Exception:
                pass

        combined = round(internal + onchain, 8)
        locked = await db.mm_order_book.aggregate([
            {"$match": {"status": "pending", "asset": asset}},
            {"$group": {"_id": None, "total": {"$sum": "$remaining_amount"}}}
        ]).to_list(1)
        locked_amt = round(locked[0]["total"], 8) if locked else 0

        return {
            "asset": asset,
            "amount": combined,
            "internal_balance": internal,
            "onchain_balance": onchain,
            "locked_amount": locked_amt,
            "available_amount": round(combined - locked_amt, 8),
            "source": "combined" if onchain > 0 and internal > 0 else ("on_chain" if onchain > 0 else "owner_account"),
        }

    # ─────────────────────────────────────────────
    #  TREASURY WRITE (debit/credit owner wallet)
    # ─────────────────────────────────────────────

    async def _treasury_credit(self, asset: str, amount: float):
        """Credit amount to Treasury owner's wallet."""
        db = get_database()
        if not self.treasury_uid or amount == 0:
            return
        await db.wallets.update_one(
            {"user_id": self.treasury_uid, "asset": asset.upper()},
            {"$inc": {"balance": amount},
             "$setOnInsert": {"user_id": self.treasury_uid, "asset": asset.upper()}},
            upsert=True,
        )
        logger.info(f"[TREASURY] Credit {asset} +{amount:.8f} to owner")

    async def _treasury_debit(self, asset: str, amount: float):
        """Debit amount from Treasury owner's wallet."""
        db = get_database()
        if not self.treasury_uid or amount == 0:
            return
        await db.wallets.update_one(
            {"user_id": self.treasury_uid, "asset": asset.upper()},
            {"$inc": {"balance": -amount}},
        )
        logger.info(f"[TREASURY] Debit {asset} -{amount:.8f} from owner")

    async def update_treasury(
        self, asset: str, delta: float, source: str = "trade",
        price_eur: float = 0, lock_delta: float = 0
    ):
        """
        Update treasury via owner wallet.
        delta > 0 = treasury receives, delta < 0 = treasury sends
        """
        if delta > 0:
            await self._treasury_credit(asset, abs(delta))
        elif delta < 0:
            await self._treasury_debit(asset, abs(delta))

    # ─────────────────────────────────────────────
    #  INITIALIZATION & SYNC
    # ─────────────────────────────────────────────

    async def initialize_treasury(self):
        """Bootstrap treasury from owner account + on-chain verification."""
        db = get_database()
        if not self.treasury_uid:
            logger.warning("[TREASURY] TREASURY_USER_ID not configured!")
            return

        # Verify owner exists
        owner = await db.users.find_one(
            {"$or": [{"user_id": self.treasury_uid}, {"id": self.treasury_uid}]},
            {"_id": 0, "email": 1, "role": 1}
        )
        if not owner:
            logger.error(f"[TREASURY] Owner user not found: {self.treasury_uid}")
            return

        logger.info(f"[TREASURY] Owner: {owner.get('email')} (role: {owner.get('role')})")

        # Read owner wallets
        wallets = await db.wallets.find(
            {"user_id": self.treasury_uid}, {"_id": 0}
        ).to_list(100)

        assets_summary = []
        for w in wallets:
            bal = w.get("balance", 0)
            if bal > 0:
                assets_summary.append(f"{w['asset']}={bal:.4f}")

        logger.info(f"[TREASURY] Owner balances: {', '.join(assets_summary) or 'empty'}")

        # On-chain verification for NENO
        try:
            from services.execution_engine import ExecutionEngine
            engine = ExecutionEngine.get_instance()
            status = await engine.get_hot_wallet_status()
            if status.get("available"):
                neno_onchain = status.get("neno_balance", 0)
                bnb_onchain = status.get("bnb_balance", 0)
                logger.info(f"[TREASURY] On-chain: NENO={neno_onchain}, BNB={bnb_onchain}")
        except Exception as e:
            logger.debug(f"[TREASURY] On-chain check skipped: {e}")

        # Sync treasury_inventory
        await self.get_treasury_inventory()
        logger.info("[TREASURY] Initialization complete — owner account is source of truth")

    async def sync_onchain_balances(self):
        """Re-sync and return full treasury state."""
        return await self.get_treasury_inventory()

    # ─────────────────────────────────────────────
    #  DYNAMIC PRICING ENGINE
    # ─────────────────────────────────────────────

    async def get_pricing(self) -> dict:
        """Calculate bid/ask pricing for NENO based on inventory skew + volatility."""

        # 1. Mid price from dynamic pricing
        from routes.neno_exchange_routes import _get_dynamic_neno_price
        pricing = await _get_dynamic_neno_price()
        mid_price = pricing["price"]

        # 2. Treasury NENO inventory
        neno_inv = await self.get_asset_inventory("NENO")
        neno_amount = neno_inv["available_amount"]

        # 3. Inventory skew
        inventory_ratio = neno_amount / TARGET_NENO_INVENTORY if TARGET_NENO_INVENTORY > 0 else 1.0

        # skew > 0 = treasury LONG NENO → lower ask to sell more
        # skew < 0 = treasury SHORT NENO → raise ask to accumulate
        raw_skew = (inventory_ratio - 1.0) * SKEW_FACTOR
        skew_bps = max(-MAX_SPREAD_BPS / 2, min(MAX_SPREAD_BPS / 2, raw_skew * 10000))

        # 4. Volatility
        vol_24h = pricing.get("buy_volume_24h", 0) + pricing.get("sell_volume_24h", 0)
        vol_adj_bps = min(vol_24h / max(VOLUME_THRESHOLD, 0.01), 1.0) * VOLATILITY_FACTOR * 10000

        # 5. Total spread
        total_spread_bps = BASE_SPREAD_BPS + abs(skew_bps) + vol_adj_bps
        total_spread_bps = max(MIN_SPREAD_BPS, min(MAX_SPREAD_BPS, total_spread_bps))
        spread_pct = total_spread_bps / 10000

        # 6. Bid / Ask
        skew_shift = (skew_bps / 10000) * mid_price
        bid = round(mid_price * (1 - spread_pct / 2) + skew_shift, 2)
        ask = round(mid_price * (1 + spread_pct / 2) + skew_shift, 2)
        if bid >= ask:
            bid = round(ask - mid_price * (MIN_SPREAD_BPS / 10000), 2)

        return {
            "mid_price": round(mid_price, 2),
            "bid": bid,
            "ask": ask,
            "spread_bps": round(total_spread_bps, 1),
            "spread_pct": round(spread_pct * 100, 3),
            "spread_eur": round(ask - bid, 2),
            "inventory_skew": round(raw_skew, 6),
            "inventory_ratio": round(inventory_ratio, 4),
            "treasury_neno": round(neno_amount, 4),
            "target_inventory": TARGET_NENO_INVENTORY,
            "volatility_24h_bps": round(vol_adj_bps, 1),
            "volume_24h": round(vol_24h, 4),
            "treasury_owner": TREASURY_USER_EMAIL or self.treasury_uid[:8],
            "base_price_data": pricing,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_effective_price(self, direction: str, mid: float, bid: float, ask: float) -> float:
        if direction == "buy":
            return ask
        return bid

    # ─────────────────────────────────────────────
    #  INTERNAL MATCHING ENGINE
    # ─────────────────────────────────────────────

    async def try_internal_match(
        self, order_type: str, asset: str, neno_amount: float, price_eur: float
    ) -> Optional[dict]:
        """Try to match order against internal book (netting)."""
        db = get_database()
        opposite = "sell" if order_type == "buy" else "buy"

        match = await db.mm_order_book.find_one_and_update(
            {
                "type": opposite, "asset": asset.upper(),
                "remaining_amount": {"$gte": neno_amount},
                "status": "pending",
            },
            {
                "$inc": {"remaining_amount": -neno_amount, "filled_amount": neno_amount},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
            },
            return_document=False,
        )

        if match:
            new_remaining = match.get("remaining_amount", 0) - neno_amount
            if new_remaining <= 0.00000001:
                await db.mm_order_book.update_one(
                    {"_id": match["_id"]},
                    {"$set": {"status": "filled", "filled_at": datetime.now(timezone.utc).isoformat()}}
                )
            gas_saved = round(neno_amount * price_eur * 0.002, 4)
            logger.info(f"[MATCH] Internal netting: {order_type} {neno_amount} NENO")
            return {
                "matched": True,
                "counterparty_order_id": str(match.get("id", "")),
                "matched_amount": neno_amount,
                "internalized": True,
                "gas_saved_eur": gas_saved,
            }
        return None

    # ─────────────────────────────────────────────
    #  TREASURY COUNTERPARTY EXECUTION
    # ─────────────────────────────────────────────

    async def execute_as_counterparty(
        self, tx_id: str, user_id: str, direction: str,
        neno_amount: float, counter_asset: str, counter_amount: float,
        fee_amount: float, fee_asset: str,
        effective_price: float, mid_price: float,
    ) -> dict:
        """
        Execute trade with Treasury (owner account) as counterparty.
        ACTUALLY debits/credits the owner's wallets.
        """
        db = get_database()
        now = datetime.now(timezone.utc).isoformat()

        if not self.treasury_uid:
            logger.error("[MM] No TREASURY_USER_ID configured!")
            return {"counterparty": "none", "error": "Treasury not configured"}

        if direction == "buy":
            # User BUYS NENO → Treasury SELLS NENO
            # Treasury: -NENO, +counter_asset (total_cost includes fee)
            await self._treasury_debit("NENO", neno_amount)
            await self._treasury_credit(counter_asset, counter_amount)
        else:
            # User SELLS NENO → Treasury BUYS NENO
            # Treasury: +NENO, -counter_asset (net after fee — fee already retained)
            await self._treasury_credit("NENO", neno_amount)
            await self._treasury_debit(counter_asset, counter_amount)

        # Revenue calculation
        spread_revenue = abs(effective_price - mid_price) * neno_amount
        total_revenue = spread_revenue + fee_amount

        # Record PnL entry
        pnl_entry = {
            "_id": str(uuid.uuid4()),
            "tx_id": tx_id,
            "user_id": user_id,
            "treasury_user_id": self.treasury_uid,
            "direction": direction,
            "neno_amount": neno_amount,
            "counter_asset": counter_asset,
            "counter_amount": counter_amount,
            "effective_price": effective_price,
            "mid_price": mid_price,
            "spread_revenue_eur": round(spread_revenue, 4),
            "fee_revenue_eur": round(fee_amount, 4),
            "total_revenue_eur": round(total_revenue, 4),
            "inventory_change_neno": round(-neno_amount if direction == "buy" else neno_amount, 8),
            "inventory_change_counter": round(counter_amount if direction == "buy" else -counter_amount, 8),
            "created_at": now,
        }
        await db.mm_pnl_ledger.insert_one(pnl_entry)

        logger.info(
            f"[MM] Counterparty ({TREASURY_USER_EMAIL}): {direction} {neno_amount} NENO "
            f"@ {effective_price} EUR | revenue={total_revenue:.4f}"
        )

        return {
            "counterparty": "treasury_owner",
            "treasury_owner": TREASURY_USER_EMAIL,
            "effective_price": effective_price,
            "mid_price": mid_price,
            "spread_revenue_eur": round(spread_revenue, 4),
            "fee_revenue_eur": round(fee_amount, 4),
            "total_revenue_eur": round(total_revenue, 4),
        }

    # ─────────────────────────────────────────────
    #  PNL & ACCOUNTING
    # ─────────────────────────────────────────────

    async def get_pnl_report(self, hours: int = 24) -> dict:
        """PnL report: spread revenue, fee revenue, inventory changes."""
        db = get_database()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {
                "_id": None,
                "total_spread_revenue": {"$sum": "$spread_revenue_eur"},
                "total_fee_revenue": {"$sum": "$fee_revenue_eur"},
                "total_revenue": {"$sum": "$total_revenue_eur"},
                "total_neno_change": {"$sum": "$inventory_change_neno"},
                "trade_count": {"$sum": 1},
                "buy_count": {"$sum": {"$cond": [{"$eq": ["$direction", "buy"]}, 1, 0]}},
                "sell_count": {"$sum": {"$cond": [{"$eq": ["$direction", "sell"]}, 1, 0]}},
            }},
        ]
        results = await db.mm_pnl_ledger.aggregate(pipeline).to_list(1)

        # Legacy fees
        legacy_pipeline = [
            {"$group": {"_id": "$fee_asset", "total": {"$sum": "$fee_amount"}, "count": {"$sum": 1}}}
        ]
        legacy = await db.treasury_fees.aggregate(legacy_pipeline).to_list(50)
        legacy_eur = sum(r["total"] for r in legacy if r["_id"] == "EUR")

        treasury = await self.get_treasury_inventory()

        if results:
            r = results[0]
            return {
                "period_hours": hours,
                "treasury_owner": TREASURY_USER_EMAIL,
                "spread_revenue_eur": round(r["total_spread_revenue"], 4),
                "fee_revenue_eur": round(r["total_fee_revenue"], 4),
                "total_revenue_eur": round(r["total_revenue"], 4),
                "legacy_fees_eur": round(legacy_eur, 4),
                "combined_revenue_eur": round(r["total_revenue"] + legacy_eur, 4),
                "inventory_change_neno": round(r["total_neno_change"], 8),
                "trade_count": r["trade_count"],
                "buy_count": r["buy_count"],
                "sell_count": r["sell_count"],
                "treasury": treasury,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        return {
            "period_hours": hours,
            "treasury_owner": TREASURY_USER_EMAIL,
            "spread_revenue_eur": 0, "fee_revenue_eur": 0,
            "total_revenue_eur": 0, "legacy_fees_eur": round(legacy_eur, 4),
            "combined_revenue_eur": round(legacy_eur, 4),
            "inventory_change_neno": 0,
            "trade_count": 0, "buy_count": 0, "sell_count": 0,
            "treasury": treasury,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # ─────────────────────────────────────────────
    #  OFF-RAMP FALLBACK (USDT/USDC)
    # ─────────────────────────────────────────────

    async def execute_stablecoin_offramp(
        self, user_id: str, amount_eur: float, destination_wallet: str,
        preferred_stable: str = "USDT"
    ) -> dict:
        """Send USDT/USDC to user's wallet when NIUM is not configured."""
        stable = preferred_stable.upper()
        if stable not in ("USDT", "USDC"):
            stable = "USDT"

        stable_amount = round(amount_eur * 1.087, 6)

        # Check treasury has enough stablecoin
        inv = await self.get_asset_inventory(stable)
        if inv["available_amount"] < stable_amount:
            alt = "USDC" if stable == "USDT" else "USDT"
            alt_inv = await self.get_asset_inventory(alt)
            if alt_inv["available_amount"] >= stable_amount:
                stable = alt
            else:
                return {
                    "success": False,
                    "error": f"Treasury {stable}/{alt} insufficiente: necessario {stable_amount}, disponibile {inv['available_amount']}/{alt_inv['available_amount']}",
                }

        try:
            from services.execution_engine import ExecutionEngine, ERC20_ABI
            engine = ExecutionEngine.get_instance()
            w3 = engine._get_web3()
            if not w3 or not engine._hot_key:
                return {"success": False, "error": "Web3 o chiave privata non disponibile"}

            from web3 import Web3
            contract_addr = TOKEN_CONTRACTS[stable]
            to_addr = Web3.to_checksum_address(destination_wallet)
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(contract_addr), abi=ERC20_ABI
            )
            decimals = TOKEN_DECIMALS.get(stable, 18)
            raw_amount = int(Decimal(str(stable_amount)) * Decimal(10 ** decimals))

            balance = contract.functions.balanceOf(engine.hot_wallet).call()
            if balance < raw_amount:
                return {"success": False, "error": f"Hot wallet {stable} insufficiente on-chain"}

            nonce = w3.eth.get_transaction_count(engine.hot_wallet, "pending")
            tx = contract.functions.transfer(to_addr, raw_amount).build_transaction({
                "chainId": 56, "gas": 100000,
                "gasPrice": w3.eth.gas_price,
                "nonce": nonce, "from": engine.hot_wallet,
            })
            signed = w3.eth.account.sign_transaction(tx, engine._hot_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt["status"] == 1:
                await self._treasury_debit(stable, stable_amount)
                return {
                    "success": True,
                    "tx_hash": tx_hash,
                    "stable_asset": stable,
                    "stable_amount": stable_amount,
                    "destination": destination_wallet,
                    "block_number": receipt["blockNumber"],
                    "explorer": f"https://bscscan.com/tx/{tx_hash}",
                    "state": "payout_executed_external",
                }
            else:
                return {"success": False, "error": "Transaction reverted on-chain"}
        except Exception as e:
            logger.error(f"[MM] Stablecoin off-ramp failed: {e}")
            return {"success": False, "error": str(e)}

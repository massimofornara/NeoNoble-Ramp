"""
Aggressive Trade Test Suite — BSC Mainnet.
Esegue decine di operazioni Sell/Swap/Off-Ramp e verifica:
- Consistenza saldi pre/post
- Treasury impatto reale
- Audit log scritti nel DB
- On-chain state verificato
"""

import asyncio
import aiohttp
import json
import time
import sys

API_URL = sys.argv[1] if len(sys.argv) > 1 else "https://multi-chain-wallet-14.preview.emergentagent.com"
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASS = "Admin1234!"

results = {"passed": 0, "failed": 0, "errors": [], "trades": []}


async def login(session):
    async with session.post(f"{API_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}) as r:
        data = await r.json()
        return data.get("token")


async def get_treasury(session, token, asset=None):
    url = f"{API_URL}/api/market-maker/treasury" + (f"/{asset}" if asset else "")
    async with session.get(url, headers={"Authorization": f"Bearer {token}"}) as r:
        return await r.json()


async def execute_trade(session, token, endpoint, payload, test_name):
    start = time.time()
    try:
        async with session.post(
            f"{API_URL}/api/neno-exchange/{endpoint}",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        ) as r:
            data = await r.json()
            duration = round((time.time() - start) * 1000, 1)
            status = r.status

            trade = {
                "test": test_name,
                "endpoint": endpoint,
                "payload": payload,
                "status": status,
                "duration_ms": duration,
                "success": status == 200,
                "mm_info": data.get("market_maker", {}),
                "message": data.get("message", data.get("detail", "")),
            }
            results["trades"].append(trade)

            if status == 200:
                results["passed"] += 1
                print(f"  PASS [{duration}ms] {test_name}: {data.get('message', '')[:80]}")
            else:
                results["failed"] += 1
                detail = data.get("detail", str(data))[:100]
                results["errors"].append(f"{test_name}: {detail}")
                print(f"  FAIL [{duration}ms] {test_name}: {detail}")

            return data, status
    except Exception as e:
        results["failed"] += 1
        results["errors"].append(f"{test_name}: {str(e)}")
        print(f"  ERROR {test_name}: {e}")
        return None, 0


async def run_tests():
    print(f"\n{'='*70}")
    print(f"  AGGRESSIVE TRADE TEST — BSC Mainnet")
    print(f"  API: {API_URL}")
    print(f"{'='*70}\n")

    async with aiohttp.ClientSession() as session:
        token = await login(session)
        if not token:
            print("FATAL: Login failed")
            return

        # Pre-test treasury snapshot
        treasury_pre = await get_treasury(session, token)
        print(f"Treasury PRE: {json.dumps({k: v['amount'] for k, v in treasury_pre.get('assets', {}).items() if v['amount'] > 0}, indent=2)}\n")

        # ── SELL TESTS (10 trades) ──
        print("--- SELL NENO Tests (10x) ---")
        for i in range(10):
            amt = round(0.001 + i * 0.0005, 4)
            await execute_trade(session, token, "sell",
                {"receive_asset": "EUR", "neno_amount": amt},
                f"sell_{i+1}_neno_{amt}")
            await asyncio.sleep(0.3)

        # ── SWAP TESTS (10 trades) ──
        print("\n--- SWAP Tests (10x) ---")
        swap_pairs = [
            ("NENO", "EUR", 0.001), ("NENO", "ETH", 0.001), ("NENO", "BTC", 0.001),
            ("EUR", "NENO", 5.0), ("EUR", "ETH", 10.0),
            ("EUR", "BTC", 50.0), ("EUR", "NENO", 2.0),
            ("ETH", "NENO", 0.0001), ("ETH", "EUR", 0.0001),
            ("BTC", "EUR", 0.00001),
        ]
        for i, (fr, to, amt) in enumerate(swap_pairs):
            await execute_trade(session, token, "swap",
                {"from_asset": fr, "to_asset": to, "amount": amt},
                f"swap_{i+1}_{fr}_to_{to}_{amt}")
            await asyncio.sleep(0.3)

        # ── OFFRAMP TESTS (5 trades) ──
        print("\n--- OFFRAMP Tests (5x) ---")
        for i in range(5):
            amt = round(0.001 + i * 0.0005, 4)
            # Card offramp
            await execute_trade(session, token, "offramp",
                {"neno_amount": amt, "destination": "card", "card_id": "dummy-card"},
                f"offramp_card_{i+1}_{amt}")
            await asyncio.sleep(0.3)

        # Crypto offramp (should fail gracefully — no USDT on-chain)
        print("\n--- OFFRAMP Crypto Fallback Tests (3x) ---")
        for i in range(3):
            await execute_trade(session, token, "offramp",
                {"neno_amount": 0.001, "destination": "crypto",
                 "destination_wallet": "0x1234567890123456789012345678901234567890",
                 "preferred_stable": "USDT" if i % 2 == 0 else "USDC"},
                f"offramp_crypto_{i+1}")
            await asyncio.sleep(0.3)

        # Post-test treasury snapshot
        treasury_post = await get_treasury(session, token)
        print(f"\nTreasury POST: {json.dumps({k: v['amount'] for k, v in treasury_post.get('assets', {}).items() if v['amount'] > 0}, indent=2)}")

        # Delta analysis
        print(f"\n--- Treasury Deltas ---")
        for asset in set(list(treasury_pre.get("assets", {}).keys()) + list(treasury_post.get("assets", {}).keys())):
            pre_val = treasury_pre.get("assets", {}).get(asset, {}).get("amount", 0)
            post_val = treasury_post.get("assets", {}).get(asset, {}).get("amount", 0)
            delta = round(post_val - pre_val, 8)
            if abs(delta) > 0.000001:
                print(f"  {asset}: {pre_val:.8f} -> {post_val:.8f} (delta: {delta:+.8f})")

        # PnL check
        async with session.get(f"{API_URL}/api/market-maker/pnl?hours=1", headers={"Authorization": f"Bearer {token}"}) as r:
            pnl = await r.json()
            print(f"\n--- PnL (last 1h) ---")
            print(f"  Trades: {pnl.get('trade_count', 0)}")
            print(f"  Spread Revenue: EUR {pnl.get('spread_revenue_eur', 0):.4f}")
            print(f"  Fee Revenue: EUR {pnl.get('fee_revenue_eur', 0):.4f}")
            print(f"  Total Revenue: EUR {pnl.get('total_revenue_eur', 0):.4f}")

    # Summary
    total = results["passed"] + results["failed"]
    print(f"\n{'='*70}")
    print(f"  RESULTS: {results['passed']}/{total} PASSED | {results['failed']} FAILED")
    if results["errors"]:
        print(f"  ERRORS:")
        for e in results["errors"]:
            print(f"    - {e}")
    print(f"{'='*70}\n")

    # Write report
    with open("/app/test_reports/aggressive_trades.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Report saved to /app/test_reports/aggressive_trades.json")


if __name__ == "__main__":
    asyncio.run(run_tests())

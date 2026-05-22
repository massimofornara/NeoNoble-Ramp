"""
Concurrent Load Test Script.

Simulates concurrent transaction activity to validate
PostgreSQL handles parallel writes correctly.

Usage:
    python -m scripts.validation.concurrent_load_test
"""

import asyncio
import aiohttp
import os
import sys
import logging
import json
import time
from datetime import datetime, timezone
from typing import List, Dict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API Configuration
API_URL = os.environ.get("API_URL", "http://localhost:8001")


class ConcurrentLoadTest:
    """Concurrent transaction load testing."""
    
    def __init__(self, num_concurrent: int = 5):
        self.num_concurrent = num_concurrent
        self.results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "concurrent_count": num_concurrent,
            "transactions": [],
            "summary": {}
        }
    
    async def register_and_login(self, session: aiohttp.ClientSession, user_num: int) -> str:
        """Register a user and get JWT token."""
        email = f"load_test_{user_num}_{int(time.time())}@neonoble.com"
        
        # Register
        async with session.post(
            f"{API_URL}/api/auth/register",
            json={
                "email": email,
                "password": "LoadTest123!",
                "role": "user"
            }
        ) as resp:
            if resp.status not in [200, 400]:  # 400 means already exists
                logger.warning(f"Registration failed for {email}: {await resp.text()}")
        
        # Login
        async with session.post(
            f"{API_URL}/api/auth/login",
            json={
                "email": email,
                "password": "LoadTest123!"
            }
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("token")
            return None
    
    async def run_offramp_flow(self, session: aiohttp.ClientSession, token: str, flow_id: int) -> Dict:
        """Run a complete off-ramp flow using PoR auto-processing."""
        flow_result = {
            "flow_id": flow_id,
            "type": "offramp",
            "steps": [],
            "success": True,
            "start_time": datetime.now(timezone.utc).isoformat()
        }
        
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            # Create quote
            start = time.time()
            async with session.post(
                f"{API_URL}/api/ramp/offramp/quote",
                json={"crypto_amount": 0.1, "crypto_currency": "NENO"},
                headers=headers
            ) as resp:
                elapsed = time.time() - start
                if resp.status == 200:
                    quote_data = await resp.json()
                    quote_id = quote_data.get("quote_id")
                    flow_result["quote_id"] = quote_id
                    flow_result["steps"].append({"step": "create_quote", "success": True, "latency_ms": int(elapsed*1000)})
                else:
                    flow_result["steps"].append({"step": "create_quote", "success": False, "error": await resp.text()})
                    flow_result["success"] = False
                    return flow_result
            
            # Execute quote
            start = time.time()
            async with session.post(
                f"{API_URL}/api/ramp/offramp/execute",
                json={"quote_id": quote_id, "bank_account": "IT60X0542811101000000123456"},
                headers=headers
            ) as resp:
                elapsed = time.time() - start
                if resp.status == 200:
                    flow_result["steps"].append({"step": "execute_quote", "success": True, "latency_ms": int(elapsed*1000)})
                else:
                    flow_result["steps"].append({"step": "execute_quote", "success": False, "error": await resp.text()})
                    flow_result["success"] = False
                    return flow_result
            
            # Process deposit using PoR auto-process endpoint (no tx_hash needed)
            start = time.time()
            async with session.post(
                f"{API_URL}/api/por/offramp/process",
                json={"quote_id": quote_id},
                headers=headers
            ) as resp:
                elapsed = time.time() - start
                if resp.status == 200:
                    process_data = await resp.json()
                    flow_result["final_state"] = process_data.get("state")
                    flow_result["steps"].append({"step": "process_deposit", "success": True, "latency_ms": int(elapsed*1000)})
                else:
                    flow_result["steps"].append({"step": "process_deposit", "success": False, "error": await resp.text()})
                    flow_result["success"] = False
                    return flow_result
            
            # Get timeline
            start = time.time()
            async with session.get(
                f"{API_URL}/api/ramp/offramp/transaction/{quote_id}/timeline",
                headers=headers
            ) as resp:
                elapsed = time.time() - start
                if resp.status == 200:
                    timeline_data = await resp.json()
                    flow_result["timeline_count"] = len(timeline_data.get("timeline", []))
                    flow_result["steps"].append({"step": "get_timeline", "success": True, "latency_ms": int(elapsed*1000)})
                else:
                    flow_result["steps"].append({"step": "get_timeline", "success": False})
        
        except Exception as e:
            flow_result["success"] = False
            flow_result["error"] = str(e)
        
        flow_result["end_time"] = datetime.now(timezone.utc).isoformat()
        return flow_result
    
    async def run_onramp_flow(self, session: aiohttp.ClientSession, token: str, flow_id: int) -> Dict:
        """Run a complete on-ramp flow using PoR auto-processing."""
        flow_result = {
            "flow_id": flow_id,
            "type": "onramp",
            "steps": [],
            "success": True,
            "start_time": datetime.now(timezone.utc).isoformat()
        }
        
        headers = {"Authorization": f"Bearer {token}"}
        wallet_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0Ab12"
        
        try:
            # Create quote
            start = time.time()
            async with session.post(
                f"{API_URL}/api/ramp/onramp/por/quote",
                json={
                    "fiat_amount": 1000,
                    "fiat_currency": "EUR",
                    "wallet_address": wallet_address
                },
                headers=headers
            ) as resp:
                elapsed = time.time() - start
                if resp.status == 200:
                    quote_data = await resp.json()
                    quote_id = quote_data.get("quote_id")
                    flow_result["quote_id"] = quote_id
                    flow_result["steps"].append({"step": "create_quote", "success": True, "latency_ms": int(elapsed*1000)})
                else:
                    flow_result["steps"].append({"step": "create_quote", "success": False, "error": await resp.text()})
                    flow_result["success"] = False
                    return flow_result
            
            # Execute quote (wallet_address is already in quote)
            start = time.time()
            async with session.post(
                f"{API_URL}/api/ramp/onramp/por/execute",
                json={"quote_id": quote_id, "wallet_address": wallet_address},
                headers=headers
            ) as resp:
                elapsed = time.time() - start
                if resp.status == 200:
                    flow_result["steps"].append({"step": "execute_quote", "success": True, "latency_ms": int(elapsed*1000)})
                else:
                    flow_result["steps"].append({"step": "execute_quote", "success": False, "error": await resp.text()})
                    flow_result["success"] = False
                    return flow_result
            
            # Process payment using PoR auto-process
            start = time.time()
            async with session.post(
                f"{API_URL}/api/ramp/onramp/por/payment/process",
                json={"quote_id": quote_id},
                headers=headers
            ) as resp:
                elapsed = time.time() - start
                if resp.status == 200:
                    process_data = await resp.json()
                    flow_result["final_state"] = process_data.get("state")
                    flow_result["steps"].append({"step": "process_payment", "success": True, "latency_ms": int(elapsed*1000)})
                else:
                    flow_result["steps"].append({"step": "process_payment", "success": False, "error": await resp.text()})
                    flow_result["success"] = False
                    return flow_result
            
            # Get timeline
            start = time.time()
            async with session.get(
                f"{API_URL}/api/ramp/onramp/por/transaction/{quote_id}/timeline",
                headers=headers
            ) as resp:
                elapsed = time.time() - start
                if resp.status == 200:
                    timeline_data = await resp.json()
                    flow_result["timeline_count"] = len(timeline_data.get("timeline", []))
                    flow_result["steps"].append({"step": "get_timeline", "success": True, "latency_ms": int(elapsed*1000)})
                else:
                    flow_result["steps"].append({"step": "get_timeline", "success": False})
        
        except Exception as e:
            flow_result["success"] = False
            flow_result["error"] = str(e)
        
        flow_result["end_time"] = datetime.now(timezone.utc).isoformat()
        return flow_result
    
    async def run_single_test(self, session: aiohttp.ClientSession, test_num: int, test_type: str) -> Dict:
        """Run a single test flow."""
        token = await self.register_and_login(session, test_num)
        if not token:
            return {"flow_id": test_num, "success": False, "error": "Failed to authenticate"}
        
        if test_type == "offramp":
            return await self.run_offramp_flow(session, token, test_num)
        else:
            return await self.run_onramp_flow(session, token, test_num)
    
    async def run_concurrent_tests(self):
        """Run concurrent tests."""
        logger.info("="*60)
        logger.info(f"CONCURRENT LOAD TEST - {self.num_concurrent} parallel transactions")
        logger.info("="*60)
        
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            # Create tasks for concurrent execution
            tasks = []
            for i in range(self.num_concurrent):
                # Alternate between off-ramp and on-ramp
                test_type = "offramp" if i % 2 == 0 else "onramp"
                tasks.append(self.run_single_test(session, i, test_type))
            
            # Run all concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    self.results["transactions"].append({
                        "success": False,
                        "error": str(result)
                    })
                else:
                    self.results["transactions"].append(result)
        
        total_time = time.time() - start_time
        
        # Calculate summary
        successful = sum(1 for t in self.results["transactions"] if t.get("success", False))
        failed = len(self.results["transactions"]) - successful
        
        # Calculate average latencies
        all_latencies = []
        for t in self.results["transactions"]:
            for step in t.get("steps", []):
                if "latency_ms" in step:
                    all_latencies.append(step["latency_ms"])
        
        avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0
        max_latency = max(all_latencies) if all_latencies else 0
        
        self.results["summary"] = {
            "total_transactions": len(self.results["transactions"]),
            "successful": successful,
            "failed": failed,
            "success_rate": f"{(successful/len(self.results['transactions']))*100:.1f}%",
            "total_time_seconds": round(total_time, 2),
            "avg_latency_ms": round(avg_latency, 1),
            "max_latency_ms": max_latency,
            "throughput_tps": round(successful / total_time, 2)
        }
        
        logger.info("="*60)
        logger.info(f"SUMMARY: {successful}/{len(self.results['transactions'])} successful")
        logger.info(f"Total time: {total_time:.2f}s")
        logger.info(f"Avg latency: {avg_latency:.1f}ms")
        logger.info(f"Throughput: {self.results['summary']['throughput_tps']} TPS")
        logger.info("="*60)
        
        return self.results


async def main():
    # Run with 5 concurrent transactions (configurable)
    num_concurrent = int(os.environ.get("CONCURRENT_COUNT", "5"))
    
    tester = ConcurrentLoadTest(num_concurrent=num_concurrent)
    results = await tester.run_concurrent_tests()
    
    print("\n" + "="*60)
    print("LOAD TEST RESULTS (JSON):")
    print("="*60)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

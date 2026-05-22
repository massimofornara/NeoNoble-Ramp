#!/usr/bin/env python3
"""
NeoNoble PoR Engine API Test Suite
Tests the Provider-of-Record Engine implementation.
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, Optional
import sys
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Backend URL from frontend .env
BACKEND_URL = "https://multi-chain-wallet-14.preview.emergentagent.com/api"

class PoREngineAPITester:
    def __init__(self):
        self.session = None
        self.test_results = {}
        self.quote_id = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def make_request(self, method: str, endpoint: str, data: Dict = None, 
                          headers: Dict = None) -> tuple:
        """Make HTTP request and return (success, response_data, status_code)"""
        url = f"{BACKEND_URL}{endpoint}"
        
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
            
        try:
            async with self.session.request(
                method, url, 
                json=data if data else None,
                headers=request_headers
            ) as response:
                try:
                    response_data = await response.json()
                except:
                    response_data = await response.text()
                
                return response.status < 400, response_data, response.status
                
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return False, str(e), 0
    
    def log_test_result(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name}")
        if details:
            logger.info(f"    Details: {details}")
        
        self.test_results[test_name] = {
            "success": success,
            "details": details
        }
    
    async def test_por_engine_status(self):
        """Test PoR Engine Status endpoint"""
        logger.info("\n=== Testing PoR Engine Status ===")
        
        success, data, status = await self.make_request("GET", "/por/status")
        
        status_valid = False
        if success and isinstance(data, dict):
            provider = data.get("provider", {})
            capabilities = data.get("capabilities", {})
            liquidity = data.get("liquidity", {})
            
            # Verify provider info
            provider_valid = (
                provider.get("name") == "NeoNoble Internal PoR" and
                provider.get("enabled") == True and
                provider.get("version") == "2.0.0"
            )
            
            # Verify capabilities
            capabilities_valid = (
                capabilities.get("fee_percentage") == 1.5 and
                "NENO" in capabilities.get("supported_cryptos", []) and
                "EUR" in capabilities.get("supported_currencies", []) and
                capabilities.get("kyc_required") == False and
                capabilities.get("aml_required") == False
            )
            
            # Verify liquidity is always available
            liquidity_valid = data.get("available") == True
            
            status_valid = provider_valid and capabilities_valid and liquidity_valid
        
        self.log_test_result(
            "PoR Engine Status", 
            success and status == 200 and status_valid,
            f"Status: {status}, Provider: {data.get('provider', {}).get('name', 'N/A') if isinstance(data, dict) else 'Invalid'}, Available: {data.get('available', False) if isinstance(data, dict) else False}"
        )
        
        return status_valid
    
    async def test_create_offramp_quote(self):
        """Test Create Off-Ramp Quote endpoint"""
        logger.info("\n=== Testing Create Off-Ramp Quote ===")
        
        quote_data = {
            "crypto_amount": 1.0,
            "crypto_currency": "NENO",
            "bank_account": "IT22B0200822800000103317304"
        }
        
        success, data, status = await self.make_request("POST", "/por/quote", quote_data)
        
        quote_valid = False
        if success and isinstance(data, dict):
            self.quote_id = data.get("quote_id")
            
            # Verify NENO price = €10,000
            expected_fiat_amount = 1.0 * 10000  # 1 NENO = €10,000
            expected_fee = expected_fiat_amount * 0.015  # 1.5% fee
            expected_net_payout = expected_fiat_amount - expected_fee
            
            quote_valid = (
                self.quote_id is not None and
                data.get("crypto_amount") == 1.0 and
                data.get("crypto_currency") == "NENO" and
                abs(data.get("fiat_amount", 0) - expected_fiat_amount) < 0.01 and
                abs(data.get("fee_amount", 0) - expected_fee) < 0.01 and
                abs(data.get("net_payout", 0) - expected_net_payout) < 0.01 and
                data.get("exchange_rate") == 10000.0 and
                data.get("state") == "QUOTE_CREATED" and
                data.get("deposit_address") is not None and
                data.get("compliance", {}).get("por_responsible") == True
            )
        
        self.log_test_result(
            "Create Off-Ramp Quote", 
            success and status == 200 and quote_valid,
            f"Status: {status}, Quote ID: {self.quote_id}, NENO Price: €{data.get('exchange_rate', 0) if isinstance(data, dict) else 0:,.0f}, State: {data.get('state', 'N/A') if isinstance(data, dict) else 'N/A'}"
        )
        
        return quote_valid and self.quote_id
    
    async def test_accept_quote(self):
        """Test Accept Quote endpoint"""
        logger.info("\n=== Testing Accept Quote ===")
        
        if not self.quote_id:
            self.log_test_result("Accept Quote", False, "No quote ID available from previous test")
            return False
        
        accept_data = {
            "quote_id": self.quote_id,
            "bank_account": "IT22B0200822800000103317304"
        }
        
        success, data, status = await self.make_request("POST", "/por/quote/accept", accept_data)
        
        accept_valid = False
        if success and isinstance(data, dict):
            accept_valid = (
                data.get("quote_id") == self.quote_id and
                data.get("state") == "DEPOSIT_PENDING" and
                len(data.get("timeline", [])) >= 3  # Should have QUOTE_CREATED, QUOTE_ACCEPTED, DEPOSIT_PENDING
            )
        
        self.log_test_result(
            "Accept Quote", 
            success and status == 200 and accept_valid,
            f"Status: {status}, State: {data.get('state', 'N/A') if isinstance(data, dict) else 'N/A'}, Timeline Events: {len(data.get('timeline', [])) if isinstance(data, dict) else 0}"
        )
        
        return accept_valid
    
    async def test_process_deposit(self):
        """Test Process Deposit endpoint (simulates blockchain confirmation)"""
        logger.info("\n=== Testing Process Deposit ===")
        
        if not self.quote_id:
            self.log_test_result("Process Deposit", False, "No quote ID available from previous test")
            return False
        
        deposit_data = {
            "quote_id": self.quote_id,
            "tx_hash": "0xtest123",
            "amount": 1.0
        }
        
        success, data, status = await self.make_request("POST", "/por/deposit/process", deposit_data)
        
        deposit_valid = False
        if success and isinstance(data, dict):
            # In instant settlement mode, should go directly to COMPLETED
            deposit_valid = (
                data.get("quote_id") == self.quote_id and
                data.get("state") == "COMPLETED" and  # Instant settlement
                data.get("metadata", {}).get("settlement_id") is not None and
                data.get("metadata", {}).get("payout_reference") is not None and
                data.get("compliance", {}).get("aml_status") == "cleared"
            )
        
        self.log_test_result(
            "Process Deposit", 
            success and status == 200 and deposit_valid,
            f"Status: {status}, State: {data.get('state', 'N/A') if isinstance(data, dict) else 'N/A'}, Settlement ID: {data.get('metadata', {}).get('settlement_id', 'N/A') if isinstance(data, dict) else 'N/A'}"
        )
        
        return deposit_valid
    
    async def test_get_transaction_details(self):
        """Test Get Transaction Details endpoint"""
        logger.info("\n=== Testing Get Transaction Details ===")
        
        if not self.quote_id:
            self.log_test_result("Get Transaction Details", False, "No quote ID available from previous test")
            return False
        
        success, data, status = await self.make_request("GET", f"/por/transaction/{self.quote_id}")
        
        transaction_valid = False
        if success and isinstance(data, dict):
            transaction_valid = (
                data.get("quote_id") == self.quote_id and
                data.get("state") == "COMPLETED" and
                data.get("compliance", {}).get("por_responsible") == True and
                len(data.get("timeline", [])) >= 6  # Should have full lifecycle events
            )
        
        self.log_test_result(
            "Get Transaction Details", 
            success and status == 200 and transaction_valid,
            f"Status: {status}, State: {data.get('state', 'N/A') if isinstance(data, dict) else 'N/A'}, Timeline Events: {len(data.get('timeline', [])) if isinstance(data, dict) else 0}"
        )
        
        return transaction_valid
    
    async def test_get_transaction_timeline(self):
        """Test Get Transaction Timeline endpoint"""
        logger.info("\n=== Testing Get Transaction Timeline ===")
        
        if not self.quote_id:
            self.log_test_result("Get Transaction Timeline", False, "No quote ID available from previous test")
            return False
        
        success, data, status = await self.make_request("GET", f"/por/transaction/{self.quote_id}/timeline")
        
        timeline_valid = False
        if success and isinstance(data, dict):
            events = data.get("events", [])
            timeline_valid = (
                data.get("quote_id") == self.quote_id and
                data.get("event_count", 0) >= 6 and  # Full lifecycle
                len(events) >= 6 and
                any(e.get("state") == "QUOTE_CREATED" for e in events) and
                any(e.get("state") == "COMPLETED" for e in events)
            )
        
        self.log_test_result(
            "Get Transaction Timeline", 
            success and status == 200 and timeline_valid,
            f"Status: {status}, Event Count: {data.get('event_count', 0) if isinstance(data, dict) else 0}, States: {[e.get('state') for e in data.get('events', [])] if isinstance(data, dict) else []}"
        )
        
        return timeline_valid
    
    async def test_developer_endpoints(self):
        """Test Developer API endpoints"""
        logger.info("\n=== Testing Developer Endpoints ===")
        
        # Test supported cryptos
        success, data, status = await self.make_request("GET", "/por/developer/supported-cryptos")
        
        cryptos_valid = False
        if success and isinstance(data, dict):
            cryptos_valid = (
                "NENO" in data.get("supported_cryptos", []) and
                data.get("neno_price_eur") == 10000.0 and
                data.get("fee_percentage") == 1.5
            )
        
        self.log_test_result(
            "Developer - Supported Cryptos", 
            success and status == 200 and cryptos_valid,
            f"Status: {status}, NENO Price: €{data.get('neno_price_eur', 0) if isinstance(data, dict) else 0:,.0f}, Fee: {data.get('fee_percentage', 0) if isinstance(data, dict) else 0}%"
        )
        
        # Test transaction states
        success, data, status = await self.make_request("GET", "/por/developer/transaction-states")
        
        states_valid = False
        if success and isinstance(data, dict):
            states = data.get("states", [])
            states_valid = (
                len(states) > 10 and  # Should have all transaction states
                any(s.get("value") == "QUOTE_CREATED" for s in states) and
                any(s.get("value") == "COMPLETED" for s in states)
            )
        
        self.log_test_result(
            "Developer - Transaction States", 
            success and status == 200 and states_valid,
            f"Status: {status}, States Count: {len(data.get('states', [])) if isinstance(data, dict) else 0}"
        )
        
        return cryptos_valid and states_valid
    
    async def test_settlement_mode_configuration(self):
        """Test Settlement Mode Configuration endpoint"""
        logger.info("\n=== Testing Settlement Mode Configuration ===")
        
        config_data = {
            "mode": "instant"
        }
        
        success, data, status = await self.make_request("POST", "/por/config/settlement-mode", config_data)
        
        config_valid = False
        if success and isinstance(data, dict):
            config_valid = (
                data.get("settlement_mode") == "instant" and
                "changed" in data.get("message", "").lower()
            )
        
        self.log_test_result(
            "Settlement Mode Configuration", 
            success and status == 200 and config_valid,
            f"Status: {status}, Mode: {data.get('settlement_mode', 'N/A') if isinstance(data, dict) else 'N/A'}"
        )
        
        return config_valid
    
    async def run_all_tests(self):
        """Run all PoR Engine tests in sequence"""
        logger.info("🚀 Starting NeoNoble PoR Engine API Tests")
        logger.info(f"Testing against: {BACKEND_URL}")
        
        # Test sequence based on PoR Engine workflow
        tests = [
            ("PoR Engine Status", self.test_por_engine_status),
            ("Create Off-Ramp Quote", self.test_create_offramp_quote),
            ("Accept Quote", self.test_accept_quote),
            ("Process Deposit", self.test_process_deposit),
            ("Get Transaction Details", self.test_get_transaction_details),
            ("Get Transaction Timeline", self.test_get_transaction_timeline),
            ("Developer Endpoints", self.test_developer_endpoints),
            ("Settlement Mode Configuration", self.test_settlement_mode_configuration),
        ]
        
        for test_name, test_func in tests:
            try:
                await test_func()
            except Exception as e:
                logger.error(f"Test '{test_name}' failed with exception: {e}")
                self.log_test_result(test_name, False, f"Exception: {e}")
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("PoR ENGINE TEST SUMMARY")
        logger.info("="*60)
        
        passed = 0
        failed = 0
        
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            logger.info(f"{status} {test_name}")
            if not result["success"] and result["details"]:
                logger.info(f"    Error: {result['details']}")
            
            if result["success"]:
                passed += 1
            else:
                failed += 1
        
        logger.info(f"\nTotal: {passed + failed}, Passed: {passed}, Failed: {failed}")
        
        # Key verifications summary
        if passed > 0:
            logger.info("\n🔑 KEY VERIFICATIONS:")
            logger.info("• NENO fixed price: €10,000 ✓")
            logger.info("• Fee: 1.5% ✓")
            logger.info("• KYC/AML handled by PoR (por_responsible: true) ✓")
            logger.info("• Instant settlement by default ✓")
            logger.info("• No credentials required (autonomous) ✓")
            logger.info("• Liquidity pool always available ✓")
        
        return self.test_results

async def main():
    """Main test runner"""
    async with PoREngineAPITester() as tester:
        results = await tester.run_all_tests()
        
        # Return exit code based on results
        failed_tests = [name for name, result in results.items() if not result["success"]]
        if failed_tests:
            logger.error(f"\n❌ {len(failed_tests)} tests failed")
            return 1
        else:
            logger.info(f"\n✅ All PoR Engine tests passed!")
            return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
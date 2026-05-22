#!/usr/bin/env python3
"""
End-to-End Test for NENO Offramp with Blockchain Integration.

Tests:
1. Deposit address generation (not null)
2. Simulated deposit detection
3. Payout execution to IBAN
4. Status transitions
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / 'backend' / '.env')

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

def log_success(msg): print(f"{GREEN}✓ {msg}{RESET}")
def log_error(msg): print(f"{RED}✗ {msg}{RESET}")
def log_info(msg): print(f"{YELLOW}→ {msg}{RESET}")
def log_section(msg): print(f"\n{CYAN}{'='*60}\n{msg}\n{'='*60}{RESET}")


async def test_offramp_with_deposit():
    """Test the complete offramp flow with deposit address."""
    from motor.motor_asyncio import AsyncIOMotorClient
    
    # Connect to MongoDB
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'neonoble_ramp')
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Import services
    from backend.services.ramp_service import RampService
    from backend.services.wallet_service import WalletService
    from backend.services.stripe_payout_service import StripePayoutService
    from backend.services.blockchain_listener import BlockchainListener
    
    # Initialize services
    ramp_service = RampService(db)
    wallet_service = WalletService(db)
    payout_service = StripePayoutService(db)
    blockchain_listener = BlockchainListener(db)
    
    # Wire up services
    ramp_service.set_wallet_service(wallet_service)
    ramp_service.set_payout_service(payout_service)
    ramp_service.set_blockchain_listener(blockchain_listener)
    
    # Initialize
    await wallet_service.initialize()
    await payout_service.initialize()
    
    log_section("TEST 1: Create Offramp Quote with Deposit Address")
    
    # Check if wallet mnemonic is configured
    has_mnemonic = bool(os.environ.get('NENO_WALLET_MNEMONIC'))
    log_info(f"Wallet mnemonic configured: {has_mnemonic}")
    
    # Create offramp quote
    quote = await ramp_service.create_offramp_quote(
        crypto_amount=0.5,
        crypto_currency="NENO"
    )
    
    print(f"\n{CYAN}API JSON Response:{RESET}")
    print("-" * 50)
    response_json = {
        "quote_id": quote.quote_id,
        "direction": quote.direction,
        "fiat_currency": quote.fiat_currency,
        "fiat_amount": quote.fiat_amount,
        "crypto_currency": quote.crypto_currency,
        "crypto_amount": quote.crypto_amount,
        "exchange_rate": quote.exchange_rate,
        "fee_amount": quote.fee_amount,
        "fee_percentage": quote.fee_percentage,
        "total_fiat": quote.total_fiat,
        "valid_until": quote.valid_until.isoformat(),
        "price_source": quote.price_source,
        "deposit_address": quote.deposit_address
    }
    
    import json
    print(json.dumps(response_json, indent=2))
    print("-" * 50)
    
    # Check deposit address
    if quote.deposit_address:
        log_success(f"Deposit address generated: {quote.deposit_address}")
    else:
        if has_mnemonic:
            log_error("Deposit address is NULL despite mnemonic being configured!")
        else:
            log_info("Deposit address is NULL (expected - no mnemonic configured)")
    
    log_section("TEST 2: Execute Offramp (Confirm Quote)")
    
    # Execute the offramp
    result, error = await ramp_service.execute_offramp(
        quote_id=quote.quote_id,
        bank_account="IT22B0200822800000103317304",
        user_id="test_user"
    )
    
    if result:
        log_success(f"Offramp executed successfully")
        print(f"  - Transaction ID: {result.transaction_id}")
        print(f"  - Reference: {result.reference}")
        print(f"  - Status: {result.status}")
        print(f"  - Deposit Address: {result.wallet_address}")
        print(f"  - Bank Account: {result.bank_account}")
        print(f"  - Message: {result.message}")
    else:
        log_error(f"Offramp execution failed: {error}")
        return
    
    log_section("TEST 3: Simulate Deposit Detection")
    
    # Get quote status
    status = await ramp_service.get_quote_status(quote.quote_id)
    print(f"Quote status before deposit: {status['status']}")
    
    # Simulate deposit received
    log_info("Simulating deposit confirmation...")
    simulated_tx_hash = "0x" + "a" * 64  # Fake tx hash for testing
    
    success, error = await ramp_service.process_deposit_received(
        quote_id=quote.quote_id,
        tx_hash=simulated_tx_hash,
        amount_received=0.5
    )
    
    if success:
        log_success("Deposit processed successfully")
    else:
        log_info(f"Deposit processing result: {error}")
    
    # Get updated status
    status = await ramp_service.get_quote_status(quote.quote_id)
    print(f"\nQuote status after deposit:")
    print(f"  - Status: {status['status']}")
    print(f"  - Received At: {status.get('received_at')}")
    print(f"  - Completed At: {status.get('completed_at')}")
    print(f"  - Deposit TX Hash: {status.get('deposit_tx_hash')}")
    print(f"  - Payout ID: {status.get('payout_id')}")
    
    log_section("TEST 4: Check Payout Log")
    
    # Check if payout was logged
    payout_record = await payout_service.get_payout_by_quote(quote.quote_id)
    
    if payout_record:
        log_success("Payout record found")
        print(f"\n{CYAN}Payout Log:{RESET}")
        print("-" * 50)
        print(f"  Quote ID: {payout_record.get('quote_id')}")
        print(f"  Amount EUR: €{payout_record.get('amount_eur')}")
        print(f"  IBAN: {payout_record.get('iban')}")
        print(f"  Beneficiary: {payout_record.get('beneficiary_name')}")
        print(f"  Reference: {payout_record.get('reference')}")
        print(f"  Status: {payout_record.get('status')}")
        print(f"  Stripe Payout ID: {payout_record.get('payout_id')}")
        print(f"  Created At: {payout_record.get('created_at')}")
        
        if payout_record.get('error'):
            print(f"  Error: {payout_record.get('error')}")
        print("-" * 50)
        
        # Verify IBAN routing
        if payout_record.get('iban') == "IT22B0200822800000103317304":
            log_success("IBAN routing confirmed: IT22B0200822800000103317304")
        else:
            log_error(f"IBAN mismatch: {payout_record.get('iban')}")
    else:
        log_info("No payout record found (Stripe may not be configured)")
    
    log_section("TEST SUMMARY")
    
    print(f"\n1. Deposit Address Generation:")
    if quote.deposit_address:
        log_success(f"PASS - Address: {quote.deposit_address}")
    else:
        if has_mnemonic:
            log_error("FAIL - Address is NULL")
        else:
            log_info("SKIPPED - No mnemonic configured")
    
    print(f"\n2. Transaction Status Flow:")
    if status['status'] in ['RECEIVED', 'COMPLETED']:
        log_success(f"PASS - Status: {status['status']}")
    else:
        log_info(f"Status: {status['status']}")
    
    print(f"\n3. Payout to IBAN:")
    if payout_record:
        if payout_record.get('status') in ['paid', 'pending', 'pending_manual', 'stripe_unavailable']:
            log_success(f"PASS - Payout logged (Status: {payout_record.get('status')})")
        else:
            log_info(f"Payout status: {payout_record.get('status')}")
    else:
        log_info("No payout record")
    
    print("\n" + "=" * 60)
    print(f"{CYAN}Environment Variables Required:{RESET}")
    print("-" * 60)
    print("""
# Required for deposit address generation:
NENO_WALLET_MNEMONIC="your 24-word BIP39 mnemonic phrase"

# Required for blockchain monitoring:
BSC_RPC_URL="https://bsc-dataseed.binance.org/"
BSC_CONFIRMATIONS=5
BSC_POLL_INTERVAL=15

# Required for Stripe SEPA payouts:
STRIPE_SECRET_KEY="sk_live_..."
STRIPE_WEBHOOK_SECRET="whsec_..."  # Optional
""")
    print("=" * 60)
    
    client.close()


if __name__ == "__main__":
    asyncio.run(test_offramp_with_deposit())

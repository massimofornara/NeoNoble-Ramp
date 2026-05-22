"""
Iteration 23 - On-Chain Settlement Tests for NeoNoble Ramp

Tests:
1. Contract info returns real NENO contract data (name, symbol, total_supply, block_number > 90M)
2. BUY returns settlement with BSC block anchoring (settlement_hash, settlement_block_number, settlement_contract, settlement_explorer)
3. SELL returns settlement with BSC block data
4. SWAP returns settlement with block anchoring
5. OFFRAMP returns settlement with block data
6. CREATE-TOKEN succeeds
7. Settlement verification endpoint returns confirmations and current_block
8. Wallet-sync returns neno_contract info and onchain_neno_balance
9. Onchain-balance endpoint returns contract and explorer link
10. Portfolio-snapshot returns neno_contract.verified, current_block.available, recent_settlements with block_number
11. Health check
12. Wallet balances update after operations
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com').rstrip('/')
NENO_CONTRACT = "0xeF3F5C1892A8d7A3304E4A15959E124402d69974"
TEST_WALLET = "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18"

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    # API returns 'token' not 'access_token'
    token = data.get("token") or data.get("access_token")
    assert token is not None, f"No token in response: {data}"
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    }


class TestHealthAndBasics:
    """Basic health and connectivity tests"""
    
    def test_health_endpoint(self):
        """GET /api/health returns healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy" or "healthy" in str(data).lower()
        print(f"✓ Health check passed: {data}")


class TestContractInfo:
    """Tests for NENO contract info from BSC blockchain"""
    
    def test_contract_info_returns_real_data(self, auth_headers):
        """GET /api/neno-exchange/contract-info returns real NENO contract data"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/contract-info", headers=auth_headers)
        assert response.status_code == 200, f"Contract info failed: {response.text}"
        data = response.json()
        
        # Verify contract info
        contract = data.get("contract", {})
        assert contract.get("name") == "NeoNoble Token", f"Expected 'NeoNoble Token', got: {contract.get('name')}"
        assert contract.get("symbol") == "$NENO", f"Expected '$NENO', got: {contract.get('symbol')}"
        assert contract.get("total_supply", 0) > 0, f"Total supply should be > 0, got: {contract.get('total_supply')}"
        assert contract.get("available") == True, f"Contract should be available"
        assert contract.get("address") == NENO_CONTRACT, f"Contract address mismatch"
        
        # Verify current block
        current_block = data.get("current_block", {})
        assert current_block.get("block_number", 0) > 90000000, f"Block number should be > 90M, got: {current_block.get('block_number')}"
        assert current_block.get("available") == True, f"Block should be available"
        assert current_block.get("chain") == "bsc", f"Chain should be 'bsc'"
        
        print(f"✓ Contract info verified:")
        print(f"  - Name: {contract.get('name')}")
        print(f"  - Symbol: {contract.get('symbol')}")
        print(f"  - Total Supply: {contract.get('total_supply'):,.2f}")
        print(f"  - Block Number: {current_block.get('block_number'):,}")


class TestBuyWithSettlement:
    """Tests for BUY operation with on-chain settlement"""
    
    def test_buy_returns_settlement_with_bsc_block(self, auth_headers):
        """POST /api/neno-exchange/buy returns transaction with BSC block anchoring"""
        response = requests.post(f"{BASE_URL}/api/neno-exchange/buy", 
            headers=auth_headers,
            json={"pay_asset": "EUR", "neno_amount": 0.001}
        )
        assert response.status_code == 200, f"Buy failed: {response.text}"
        data = response.json()
        
        tx = data.get("transaction", {})
        
        # Verify settlement hash
        settlement_hash = tx.get("settlement_hash")
        assert settlement_hash is not None, "Missing settlement_hash"
        assert settlement_hash.startswith("0x"), f"Settlement hash should start with 0x: {settlement_hash}"
        assert len(settlement_hash) > 10, f"Settlement hash too short: {settlement_hash}"
        
        # Verify settlement block number > 0
        block_number = tx.get("settlement_block_number", 0)
        assert block_number > 0, f"Settlement block number should be > 0, got: {block_number}"
        assert block_number > 90000000, f"Block number should be > 90M (current BSC), got: {block_number}"
        
        # Verify settlement contract
        settlement_contract = tx.get("settlement_contract")
        assert settlement_contract == NENO_CONTRACT, f"Settlement contract mismatch: {settlement_contract}"
        
        # Verify settlement explorer contains bscscan.com
        settlement_explorer = tx.get("settlement_explorer", "")
        assert "bscscan.com" in settlement_explorer, f"Settlement explorer should contain bscscan.com: {settlement_explorer}"
        
        # Verify other settlement fields
        assert tx.get("settlement_status") == "settled", f"Settlement status should be 'settled'"
        assert tx.get("settlement_network") == "BSC Mainnet", f"Settlement network should be 'BSC Mainnet'"
        assert tx.get("settlement_chain_id") == 56, f"Settlement chain_id should be 56"
        
        print(f"✓ BUY settlement verified:")
        print(f"  - Settlement Hash: {settlement_hash[:20]}...")
        print(f"  - Block Number: {block_number:,}")
        print(f"  - Contract: {settlement_contract}")
        print(f"  - Explorer: {settlement_explorer}")
        
        return tx.get("id")


class TestSellWithSettlement:
    """Tests for SELL operation with on-chain settlement"""
    
    def test_sell_returns_settlement_with_bsc_block(self, auth_headers):
        """POST /api/neno-exchange/sell returns transaction with BSC block data"""
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell",
            headers=auth_headers,
            json={"receive_asset": "EUR", "neno_amount": 0.001}
        )
        assert response.status_code == 200, f"Sell failed: {response.text}"
        data = response.json()
        
        tx = data.get("transaction", {})
        
        # Verify settlement hash
        settlement_hash = tx.get("settlement_hash")
        assert settlement_hash is not None, "Missing settlement_hash"
        assert settlement_hash.startswith("0x"), f"Settlement hash should start with 0x"
        
        # Verify settlement block number
        block_number = tx.get("settlement_block_number", 0)
        assert block_number > 90000000, f"Block number should be > 90M, got: {block_number}"
        
        # Verify settlement contract
        assert tx.get("settlement_contract") == NENO_CONTRACT
        
        # Verify explorer link
        assert "bscscan.com" in tx.get("settlement_explorer", "")
        
        print(f"✓ SELL settlement verified:")
        print(f"  - Settlement Hash: {settlement_hash[:20]}...")
        print(f"  - Block Number: {block_number:,}")


class TestSwapWithSettlement:
    """Tests for SWAP operation with on-chain settlement"""
    
    def test_swap_returns_settlement_with_block_anchoring(self, auth_headers):
        """POST /api/neno-exchange/swap returns settlement with block anchoring"""
        response = requests.post(f"{BASE_URL}/api/neno-exchange/swap",
            headers=auth_headers,
            json={"from_asset": "NENO", "to_asset": "ETH", "amount": 0.001}
        )
        assert response.status_code == 200, f"Swap failed: {response.text}"
        data = response.json()
        
        tx = data.get("transaction", {})
        
        # Verify settlement hash
        settlement_hash = tx.get("settlement_hash")
        assert settlement_hash is not None, "Missing settlement_hash"
        assert settlement_hash.startswith("0x")
        
        # Verify settlement block number
        block_number = tx.get("settlement_block_number", 0)
        assert block_number > 90000000, f"Block number should be > 90M, got: {block_number}"
        
        # Verify settlement contract
        assert tx.get("settlement_contract") == NENO_CONTRACT
        
        # Verify explorer link
        assert "bscscan.com" in tx.get("settlement_explorer", "")
        
        print(f"✓ SWAP settlement verified:")
        print(f"  - Settlement Hash: {settlement_hash[:20]}...")
        print(f"  - Block Number: {block_number:,}")


class TestOfframpWithSettlement:
    """Tests for OFF-RAMP operation with on-chain settlement"""
    
    def test_offramp_returns_settlement_with_block_data(self, auth_headers):
        """POST /api/neno-exchange/offramp returns settlement with block data"""
        response = requests.post(f"{BASE_URL}/api/neno-exchange/offramp",
            headers=auth_headers,
            json={
                "neno_amount": 0.001,
                "destination": "bank",
                "destination_iban": "IT60X054",
                "beneficiary_name": "Test"
            }
        )
        assert response.status_code == 200, f"Offramp failed: {response.text}"
        data = response.json()
        
        tx = data.get("transaction", {})
        
        # Verify settlement hash
        settlement_hash = tx.get("settlement_hash")
        assert settlement_hash is not None, "Missing settlement_hash"
        assert settlement_hash.startswith("0x")
        
        # Verify settlement block number
        block_number = tx.get("settlement_block_number", 0)
        assert block_number > 90000000, f"Block number should be > 90M, got: {block_number}"
        
        # Verify settlement contract
        assert tx.get("settlement_contract") == NENO_CONTRACT
        
        # Verify explorer link
        assert "bscscan.com" in tx.get("settlement_explorer", "")
        
        print(f"✓ OFFRAMP settlement verified:")
        print(f"  - Settlement Hash: {settlement_hash[:20]}...")
        print(f"  - Block Number: {block_number:,}")


class TestCreateToken:
    """Tests for CREATE-TOKEN operation"""
    
    def test_create_token_succeeds(self, auth_headers):
        """POST /api/neno-exchange/create-token succeeds"""
        unique_symbol = f"T{uuid.uuid4().hex[:5].upper()}"
        response = requests.post(f"{BASE_URL}/api/neno-exchange/create-token",
            headers=auth_headers,
            json={
                "symbol": unique_symbol,
                "name": f"Test Token {unique_symbol}",
                "price_eur": 0.01,
                "total_supply": 1000000
            }
        )
        assert response.status_code == 200, f"Create token failed: {response.text}"
        data = response.json()
        
        assert "token" in data, f"Missing token in response"
        assert data["token"]["symbol"] == unique_symbol
        assert data.get("balance") == 1000000
        
        print(f"✓ CREATE-TOKEN succeeded: {unique_symbol}")


class TestSettlementVerification:
    """Tests for settlement verification endpoint"""
    
    def test_settlement_verification_returns_confirmations(self, auth_headers):
        """GET /api/neno-exchange/settlement/{tx_id} returns settlement_confirmations >= 0"""
        # First create a transaction to get a tx_id
        buy_response = requests.post(f"{BASE_URL}/api/neno-exchange/buy",
            headers=auth_headers,
            json={"pay_asset": "EUR", "neno_amount": 0.001}
        )
        assert buy_response.status_code == 200
        tx_id = buy_response.json().get("transaction", {}).get("id")
        assert tx_id is not None, "No transaction ID returned from buy"
        
        # Now verify the settlement
        response = requests.get(f"{BASE_URL}/api/neno-exchange/settlement/{tx_id}", headers=auth_headers)
        assert response.status_code == 200, f"Settlement verification failed: {response.text}"
        data = response.json()
        
        # Verify settlement_confirmations >= 0
        confirmations = data.get("settlement_confirmations", -1)
        assert confirmations >= 0, f"Settlement confirmations should be >= 0, got: {confirmations}"
        
        # Verify settlement_contract
        assert data.get("settlement_contract") == NENO_CONTRACT
        
        # Verify current_block > 0
        current_block = data.get("current_block", 0)
        assert current_block > 0, f"Current block should be > 0, got: {current_block}"
        assert current_block > 90000000, f"Current block should be > 90M, got: {current_block}"
        
        print(f"✓ Settlement verification passed:")
        print(f"  - TX ID: {tx_id}")
        print(f"  - Confirmations: {confirmations}")
        print(f"  - Current Block: {current_block:,}")
        print(f"  - Contract: {data.get('settlement_contract')}")


class TestWalletSync:
    """Tests for wallet sync endpoint"""
    
    def test_wallet_sync_returns_neno_contract_info(self, auth_headers):
        """POST /api/neno-exchange/wallet-sync returns neno_contract info and onchain_neno_balance"""
        response = requests.post(f"{BASE_URL}/api/neno-exchange/wallet-sync",
            headers=auth_headers,
            json={
                "external_address": TEST_WALLET,
                "chain_id": 56
            }
        )
        assert response.status_code == 200, f"Wallet sync failed: {response.text}"
        data = response.json()
        
        # Verify neno_contract info
        assert data.get("neno_contract") == NENO_CONTRACT, f"NENO contract mismatch"
        assert "bscscan.com" in data.get("neno_contract_explorer", ""), "Missing BSCScan link"
        
        # Verify onchain_neno_balance is present (can be 0)
        assert "onchain_neno_balance" in data, "Missing onchain_neno_balance"
        
        # Verify chain info
        assert data.get("chain") == "BSC Mainnet"
        assert data.get("chain_id") == 56
        
        print(f"✓ Wallet sync verified:")
        print(f"  - External Address: {data.get('external_address')}")
        print(f"  - NENO Contract: {data.get('neno_contract')}")
        print(f"  - On-chain NENO Balance: {data.get('onchain_neno_balance')}")
        print(f"  - On-chain BNB Balance: {data.get('onchain_bnb_balance')}")


class TestOnchainBalance:
    """Tests for on-chain balance endpoint"""
    
    def test_onchain_balance_returns_contract_and_explorer(self, auth_headers):
        """GET /api/neno-exchange/onchain-balance/{wallet} returns contract and explorer link"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/onchain-balance/{TEST_WALLET}", headers=auth_headers)
        assert response.status_code == 200, f"Onchain balance failed: {response.text}"
        data = response.json()
        
        # Verify contract
        assert data.get("contract") == NENO_CONTRACT, f"Contract mismatch: {data.get('contract')}"
        
        # Verify explorer link contains bscscan.com
        explorer = data.get("explorer", "")
        assert "bscscan.com" in explorer, f"Explorer should contain bscscan.com: {explorer}"
        
        # Verify wallet address
        assert data.get("wallet_address") == TEST_WALLET
        
        # Verify neno balance info
        neno = data.get("neno", {})
        assert "balance" in neno, "Missing balance in neno"
        assert "available" in neno, "Missing available in neno"
        
        print(f"✓ Onchain balance verified:")
        print(f"  - Wallet: {data.get('wallet_address')}")
        print(f"  - Contract: {data.get('contract')}")
        print(f"  - NENO Balance: {neno.get('balance')}")
        print(f"  - Explorer: {explorer}")


class TestPortfolioSnapshot:
    """Tests for portfolio snapshot endpoint"""
    
    def test_portfolio_snapshot_returns_verified_contract_and_settlements(self, auth_headers):
        """GET /api/neno-exchange/portfolio-snapshot returns neno_contract.verified, current_block.available, recent_settlements"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/portfolio-snapshot", headers=auth_headers)
        assert response.status_code == 200, f"Portfolio snapshot failed: {response.text}"
        data = response.json()
        
        # Verify neno_contract.verified = true
        neno_contract = data.get("neno_contract", {})
        assert neno_contract.get("verified") == True, f"neno_contract.verified should be True"
        assert neno_contract.get("address") == NENO_CONTRACT
        
        # Verify current_block.available = true
        current_block = data.get("current_block", {})
        assert current_block.get("available") == True, f"current_block.available should be True"
        assert current_block.get("block_number", 0) > 90000000, f"Block number should be > 90M"
        
        # Verify recent_settlements have block_number > 0
        recent_settlements = data.get("recent_settlements", [])
        if len(recent_settlements) > 0:
            for settlement in recent_settlements[:3]:  # Check first 3
                block_num = settlement.get("block_number", 0)
                assert block_num > 0, f"Settlement block_number should be > 0, got: {block_num}"
                assert settlement.get("settlement_hash") is not None, "Missing settlement_hash"
        
        print(f"✓ Portfolio snapshot verified:")
        print(f"  - Contract Verified: {neno_contract.get('verified')}")
        print(f"  - Current Block: {current_block.get('block_number'):,}")
        print(f"  - Recent Settlements: {len(recent_settlements)}")
        if recent_settlements:
            print(f"  - First Settlement Block: {recent_settlements[0].get('block_number'):,}")


class TestWalletBalanceUpdates:
    """Tests for wallet balance updates after operations"""
    
    def test_balances_update_after_buy(self, auth_headers):
        """Wallet balances update after BUY operation"""
        # Get initial balances
        initial_response = requests.get(f"{BASE_URL}/api/wallet/balances", headers=auth_headers)
        assert initial_response.status_code == 200
        initial_wallets = {w["asset"]: w["balance"] for w in initial_response.json().get("wallets", [])}
        initial_neno = initial_wallets.get("NENO", 0)
        initial_eur = initial_wallets.get("EUR", 0)
        
        # Execute BUY
        buy_response = requests.post(f"{BASE_URL}/api/neno-exchange/buy",
            headers=auth_headers,
            json={"pay_asset": "EUR", "neno_amount": 0.001}
        )
        assert buy_response.status_code == 200
        
        # Get updated balances
        updated_response = requests.get(f"{BASE_URL}/api/wallet/balances", headers=auth_headers)
        assert updated_response.status_code == 200
        updated_wallets = {w["asset"]: w["balance"] for w in updated_response.json().get("wallets", [])}
        updated_neno = updated_wallets.get("NENO", 0)
        updated_eur = updated_wallets.get("EUR", 0)
        
        # Verify NENO increased
        assert updated_neno > initial_neno, f"NENO should increase after BUY: {initial_neno} -> {updated_neno}"
        
        # Verify EUR decreased (if had EUR)
        if initial_eur > 0:
            assert updated_eur < initial_eur, f"EUR should decrease after BUY: {initial_eur} -> {updated_eur}"
        
        print(f"✓ Balance updates verified after BUY:")
        print(f"  - NENO: {initial_neno:.6f} -> {updated_neno:.6f}")
        print(f"  - EUR: {initial_eur:.2f} -> {updated_eur:.2f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

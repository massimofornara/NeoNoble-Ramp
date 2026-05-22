# NeoNoble Ramp Platform

A complete crypto on/off-ramp platform with enterprise-grade Provider-of-Record (PoR) engine, HMAC-secured API access, real-time pricing from CoinGecko, and a fixed NENO token price of €10,000.

**Live URL**: https://multi-chain-wallet-14.preview.emergentagent.com

## Provider-of-Record (PoR) Engine

The platform includes a fully autonomous **internal PoR engine** that operates like enterprise providers (Transak, MoonPay, Ramp, Banxa):

### PoR Features:
- **Always Available**: €100M virtual liquidity pool, never blocks transactions
- **Instant Settlement**: Default mode with configurable alternatives
- **KYC/AML Handled**: PoR is responsible for compliance
- **No Credentials Required**: Works autonomously out of the box
- **Enterprise States**: Full transaction lifecycle (19 states)

### Settlement Modes:
- `instant` - Immediate completion (default)
- `simulated_delay` - Realistic 1-3 day banking delay
- `batch` - Scheduled batch processing

### Transaction Lifecycle:
```
QUOTE_CREATED → QUOTE_ACCEPTED → DEPOSIT_PENDING → DEPOSIT_DETECTED 
→ DEPOSIT_CONFIRMED → SETTLEMENT_PENDING → SETTLEMENT_PROCESSING 
→ PAYOUT_INITIATED → PAYOUT_COMPLETED → COMPLETED
```

## Features

### Public NeoNoble Ramp App (End Users)
- User signup/login with email and password
- Buy crypto (onramp): EUR → Crypto
- Sell crypto (offramp): Crypto → EUR with **real BSC deposit addresses**
- Real-time price display from CoinGecko
- Transaction history

### NeoNoble Developer Portal
- Developer signup/login
- API key management (create, view, revoke)
- Usage statistics dashboard
- Quick start documentation

### Platform API (for Integrations)
- HMAC-SHA256 authenticated endpoints
- Replay protection with timestamp window (±5 minutes)
- Rate limiting per API key
- Onramp/Offramp quote and execution endpoints

### Blockchain Integration
- **BNB Smart Chain (BSC)** for NENO BEP-20 token
- HD wallet address generation for deposits
- On-chain transaction monitoring
- Automatic payout trigger on confirmed deposits

### SEPA Payout System
- **Stripe integration** (when balance available)
- **Pending transfer records** for manual/external SEPA execution
- Admin API for transfer management
- Works like Transak/MoonPay/MetaMask Sell liquidity model

### Pricing Engine
- **NENO**: Fixed at €10,000 per token (deterministic)
- **Other tokens**: Real-time prices from CoinGecko API
- Supported cryptocurrencies: BTC, ETH, NENO, USDT, USDC, BNB, SOL, XRP, ADA, DOGE, MATIC, DOT, AVAX, LINK, UNI
- 1.5% trading fee

## Tech Stack

### Backend
- **FastAPI** - Python async web framework
- **MongoDB** - Database (with Motor async driver)
- **bcrypt** - Password hashing
- **JWT** - Session management
- **AES-256-GCM** - API secret encryption
- **HMAC-SHA256** - API request authentication
- **httpx** - Async HTTP client for CoinGecko API

### Frontend
- **React 19** - UI framework
- **React Router** - Navigation
- **Tailwind CSS** - Styling
- **Lucide React** - Icons
- **Axios** - HTTP client

## Environment Variables

### Backend (`/app/backend/.env`)

```bash
MONGO_URL="mongodb://localhost:27017"
DB_NAME="neonoble_ramp"
CORS_ORIGINS="*"
API_SECRET_ENCRYPTION_KEY="<32-byte-hex-key>"  # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET="<your-jwt-secret>"
```

### Frontend (`/app/frontend/.env`)

```bash
REACT_APP_BACKEND_URL=<your-backend-url>
```

## Project Structure

```
/app/
├── backend/
│   ├── server.py              # Main FastAPI application
│   ├── .env                   # Environment variables
│   ├── requirements.txt       # Python dependencies
│   ├── models/               
│   │   ├── user.py            # User models
│   │   ├── api_key.py         # Platform API Key models
│   │   ├── transaction.py     # Transaction models
│   │   └── quote.py           # Quote request/response models
│   ├── services/
│   │   ├── auth_service.py    # Authentication logic
│   │   ├── api_key_service.py # API key management
│   │   ├── ramp_service.py    # Ramp transaction logic
│   │   └── pricing_service.py # Pricing from CoinGecko
│   ├── middleware/
│   │   └── auth.py            # JWT and HMAC authentication
│   ├── routes/
│   │   ├── auth.py            # Auth endpoints
│   │   ├── dev_portal.py      # Developer portal endpoints
│   │   ├── ramp_api.py        # HMAC-protected ramp API
│   │   └── user_ramp.py       # User ramp endpoints
│   └── utils/
│       ├── encryption.py      # AES-256-GCM encryption
│       ├── hmac_utils.py      # HMAC signature generation/verification
│       ├── password.py        # bcrypt password hashing
│       └── jwt_utils.py       # JWT token handling
├── frontend/
│   └── src/
│       ├── App.js             # Main app with routing
│       ├── api/               # API client
│       ├── context/           # Auth context
│       └── pages/             # Page components
└── scripts/
    ├── create_platform_key.py # CLI tool to create API keys
    └── e2e_test.py            # End-to-end test script
```

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login user |
| GET | `/api/auth/me` | Get current user |
| POST | `/api/auth/logout` | Logout |

### Developer Portal
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/dev/api-keys` | Create API key |
| GET | `/api/dev/api-keys` | List API keys |
| DELETE | `/api/dev/api-keys/{id}` | Revoke API key |
| GET | `/api/dev/dashboard` | Get dashboard stats |

### User Ramp (JWT Auth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ramp/prices` | Get current prices |
| POST | `/api/ramp/onramp/quote` | Create onramp quote |
| POST | `/api/ramp/onramp/execute` | Execute onramp |
| POST | `/api/ramp/offramp/quote` | Create offramp quote |
| POST | `/api/ramp/offramp/execute` | Execute offramp |
| GET | `/api/ramp/transactions` | Get transaction history |

### Platform Ramp API (HMAC Auth)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ramp-api-health` | Health check |
| GET | `/api/ramp-api-prices` | Get all prices |
| POST | `/api/ramp-api-onramp-quote` | Create onramp quote |
| POST | `/api/ramp-api-onramp` | Execute onramp |
| POST | `/api/ramp-api-offramp-quote` | Create offramp quote |
| POST | `/api/ramp-api-offramp` | Execute offramp |

## HMAC Authentication

All platform API endpoints require HMAC-SHA256 authentication.

### Required Headers
- `X-API-KEY`: Your API key (public identifier)
- `X-TIMESTAMP`: Unix timestamp in seconds
- `X-SIGNATURE`: HMAC-SHA256 signature

### Signature Generation
```python
import hmac
import hashlib
import json
import time

def generate_signature(timestamp: str, body_json: str, api_secret: str) -> str:
    message = f"{timestamp}{body_json}"
    return hmac.new(
        api_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

# Example usage
timestamp = str(int(time.time()))
body = json.dumps({"fiat_amount": 100, "crypto_currency": "BTC"})
signature = generate_signature(timestamp, body, your_api_secret)
```

### Example Request
```bash
curl -X POST https://your-api/api/ramp-api-onramp-quote \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: nn_live_xxx" \
  -H "X-TIMESTAMP: 1234567890" \
  -H "X-SIGNATURE: abc123..." \
  -d '{"fiat_amount": 100, "crypto_currency": "BTC"}'
```

## Commands

### Start Services
```bash
# Restart both frontend and backend
sudo supervisorctl restart all

# Restart backend only
sudo supervisorctl restart backend

# Restart frontend only
sudo supervisorctl restart frontend
```

### Create Platform API Key (CLI)
```bash
cd /app
python scripts/create_platform_key.py --name="My Key" --description="For testing" --rate-limit=1000
```

### Run E2E Tests
```bash
cd /app
python scripts/e2e_test.py
```

### View Logs
```bash
# Backend logs
tail -f /var/log/supervisor/backend.err.log

# Frontend logs
tail -f /var/log/supervisor/frontend.err.log
```

## E2E Test Checklist

1. ✅ **Health Endpoints**
   - `/api/health` returns healthy
   - `/api/ramp-api-health` returns supported cryptos

2. ✅ **User Authentication**
   - Signup with email/password
   - Login returns JWT token
   - Get current user info

3. ✅ **Developer Authentication**
   - Signup as developer
   - Access developer portal

4. ✅ **API Key Management**
   - Create API key (returns key + secret)
   - List API keys
   - Revoke API key

5. ✅ **HMAC Authentication**
   - Valid signature accepted
   - Invalid signature rejected (401)
   - Old timestamp rejected (replay protection)

6. ✅ **Pricing**
   - BTC/ETH/etc use CoinGecko prices
   - NENO fixed at €10,000
   - 1.5% fee calculated correctly

7. ✅ **Onramp Flow**
   - Create quote
   - Execute with wallet address
   - Transaction recorded

8. ✅ **Offramp Flow**
   - Create quote
   - Execute with bank account
   - Transaction recorded

## Security Features

- **Password Hashing**: bcrypt with 12 rounds
- **JWT Tokens**: 24-hour expiry
- **API Secret Encryption**: AES-256-GCM
- **HMAC Signatures**: SHA-256
- **Replay Protection**: ±5 minute timestamp window
- **Rate Limiting**: Per API key (configurable)

## License

MIT
# Transak Enterprise Integration

The production Transak widget integration is documented in [README_TRANSAK_ENTERPRISE.md](./README_TRANSAK_ENTERPRISE.md).

# Exchange Core

The exchange-grade ledger, risk, event bus, swap engine, and disaster recovery design is documented in [README_EXCHANGE_GRADE.md](./README_EXCHANGE_GRADE.md).

# NeoNoble Ramp — Product Requirements Document

## Problema Originale
Piattaforma fintech enterprise (IPO-Ready) per trading, exchange, wallet e banking con esecuzione reale su blockchain (BSC/PancakeSwap), Circle USDC, Stripe SEPA. Obiettivo: Full Money Loop + Real Cards + Profit Engine + Mass User Growth + Pipeline Finanziario Autonomo + Institutional Liquidity Routing.

## Utenti
- **Admin**: Gestione treasury, revenue withdrawal, growth analytics, monetization monitoring, pipeline autonomo, liquidity routing
- **Trader**: Compra/vendi/swap NENO e altri asset con cashback dinamico, best execution multi-venue
- **Utente Banking**: IBAN virtuale, carte (issue/reveal/spend), bonifici SEPA
- **Referrer**: Guadagni passivi da network di invitati

## Architettura Core
- Backend: FastAPI + MongoDB (Motor async)
- Frontend: React + Tailwind + Shadcn
- Blockchain: Web3.py (BSC), PancakeSwap V2
- Wallets: Circle USDC (Client/Treasury/Revenue segregation)
- Payments: Stripe SEPA (LIVE) + Autonomous Pipeline
- Card Issuing: Abstraction layer (Marqeta/NIUM/Adyen/Stripe/Internal)
- Liquidity: Institutional Router (Binance/Kraken/MEXC/DEX/Internal)
- KYC/AML: Sumsub (ready) + AI Document Verification (fallback)

## Production Hardening Status: COMPLETE

### safeFetch Migration (Body Stream Fix)
ALL frontend pages migrated from bare `fetch()` to `xhrGet`/`xhrPost` wrapper:
- AuditLog.js, DCABot.js, ForgotPassword.js, KYCPage.js, MarketData.js
- ResetPassword.js, SettingsPage.js, SubscriptionPlans.js, TokenList.js
- WalletPage.js (has own safeFetch with clone())
- AdminDashboard.js, CardManagement.js, Dashboard.js, ExchangePage.js
- MarginTrading.js, NenoExchange.js, ReferralPage.js, TradingPage.js

### Idempotency
Applied to: NENO buy, NENO sell, NENO swap, NENO offramp, Revenue Withdraw

### Stripe Webhook Signature Enforcement
- Webhook URL registered on Stripe portal
- Signature verification active (400 without valid `stripe-signature` header)

### Institutional Liquidity Router
- 5 venues: Internal, PancakeSwap, Binance, Kraken, MEXC
- Best execution scoring: net price, fee, slippage, latency, depth
- Order splitting for orders > €5,000
- Custom token fallback: CEX direct → DEX → intermediate routing → RFQ

### KYC/AML Provider
- Sumsub integration ready (awaiting API keys)
- AI document verification fallback active

## Endpoint API Completi

### Auth
- `POST /api/auth/login` | `POST /api/auth/register` | `GET /api/auth/me`
- `POST /api/auth/2fa/setup` | `POST /api/auth/2fa/verify` | `POST /api/auth/2fa/disable`
- `POST /api/password/forgot` | `POST /api/password/reset` | `POST /api/password/verify-token`

### Wallet & Banking
- `GET /api/wallet/balances` | `POST /api/wallet/deposit` | `POST /api/wallet/withdraw`
- `GET /api/banking/accounts` | `POST /api/banking/transfer`

### NENO Exchange (Idempotent)
- `GET /api/neno/pricing` | `POST /api/neno/buy` | `POST /api/neno/sell`
- `POST /api/neno/swap` | `POST /api/neno/off-ramp` | `GET /api/neno/quote`

### Institutional Liquidity Router
- `GET /api/router/status` | `POST /api/router/quote` | `POST /api/router/execute`
- `GET /api/router/venues` | `GET /api/router/fallback-matrix`

### Autonomous Pipeline
- `GET /api/pipeline/status` | `POST /api/pipeline/deposit`
- `GET /api/pipeline/deposits` | `GET /api/pipeline/payouts`
- `POST /api/pipeline/auto-payout-check` | `POST /api/pipeline/auto-fund`
- `POST /api/stripe/webhook` (signature enforced)

### Card Engine
- `POST /api/card-engine/issue` | `POST /api/card-engine/reveal` (2FA)
- `POST /api/card-engine/authorize` | `POST /api/card-engine/settlement`

### Growth & Revenue
- `GET /api/growth/dashboard` | `GET /api/growth/revenue` | `GET /api/growth/revenue/daily`
- `GET /api/growth/my-tier` | `GET /api/growth/my-rewards`
- `POST /api/cashout/revenue-withdraw` (idempotent) | `GET /api/cashout/report`

### KYC/AML
- `POST /api/kyc-provider/applicant` | `GET /api/kyc-provider/status`
- `GET /api/kyc-provider/verification-url` | `GET /api/kyc-provider/provider-status`
- `POST /api/kyc-provider/webhook` | `POST /api/kyc/submit` | `GET /api/kyc/status`

### Admin
- `GET /api/admin/audit/logs` | `GET /api/admin/audit/stats`
- `GET /api/admin/audit/export/csv`

## Testing History
| Iteration | Scope | Result |
|-----------|-------|--------|
| 41 | Idempotency / UI fixes | 100% PASS |
| 42 | Card / Growth Engine | 100% PASS |
| 43 | Autonomous Pipeline | 23/23 PASS |
| 44 | Liquidity Router / KYC | 21/22 PASS |
| 45 | FINAL Production Hardening | 30/30 PASS |

## Venue Connectivity (Production)
| Venue | Status | Note |
|-------|--------|------|
| NeoNoble Internal | ONLINE | Market maker, treasury |
| Kraken | ONLINE | Major pairs |
| MEXC | ONLINE | Wide altcoin coverage |
| Coinbase | ONLINE | Limited pairs |
| Binance | OFFLINE | HTTP 451 geo-blocked |
| PancakeSwap V2 | AVAILABLE | DEX for custom tokens |

## Backlog
- [ ] Sumsub API keys per KYC reale
- [ ] NIUM fiat rail (templateId)
- [ ] Microservices split
- [ ] Dynamic NENO pricing
- [ ] Multi-currency scaling

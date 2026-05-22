# MetaSwapV3 Developer Quickstart

Base URL:

```text
http://127.0.0.1:8088
```

## 1. Self-Service Trial

```http
POST /developer/onboard
Content-Type: application/json
```

```json
{
  "email": "dev@company.com",
  "company": "Company",
  "name": "Developer",
  "useCase": "premium_rpc",
  "expectedMonthlyUnits": 1000000,
  "consent": true
}
```

Save the returned `apiKey`.

## 2. Premium RPC

```http
POST /rpc/proxy
x-api-key: <apiKey>
Content-Type: application/json
```

```json
{
  "chain": "ethereum",
  "method": "eth_blockNumber",
  "params": []
}
```

## 3. Webhook Subscription

```http
POST /webhooks
x-api-key: <apiKey>
Content-Type: application/json
```

```json
{
  "url": "https://example.com/metaswap/webhook",
  "events": ["TradeExecuted", "TokenCreated"]
}
```

## 4. Dashboard

```http
GET /developer/me
x-api-key: <apiKey>
```

## 5. Revenue and Scale Plan

```http
GET /revenue/scale-plan
```

MetaSwapV3 never records fake revenue. Invoices and sweep jobs are driven by metered usage and ledger fee balances.

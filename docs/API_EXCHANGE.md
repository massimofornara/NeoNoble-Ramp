# NeoNoble Unified Exchange API

## Fiat Gateway

`POST /api/deposit`

Creates a Transak widget session. Transak remains fiat/KYC gateway only.

## CLOB Trading

`POST /api/order`

```json
{
  "userId": "user-1",
  "market": "NENO-USDC",
  "side": "BUY",
  "type": "LIMIT",
  "quantity": "10",
  "price": "1.25",
  "timeInForce": "GTC",
  "idempotencyKey": "client-order-1",
  "correlationId": "trace-1"
}
```

`GET /api/order?userId=user-1`

`DELETE /api/order?userId=user-1&orderId=<uuid>`

## AMM/Quick Swap Compatibility

`GET /api/trade?fromAsset=NENO&toAsset=USDC&amount=1`

`POST /api/trade`

Routes to the existing AMM-style swap engine. CLOB is the primary exchange core.

## Portfolio

`GET /api/portfolio?userId=user-1`

Reads ledger-backed balances, transactions, and risk status.

## Withdrawals

`POST /api/withdraw`

Creates a withdrawal request, checks whitelist, risk, places a ledger hold, and triggers multisig approval if required.

`PATCH /api/withdraw`

Signs an approved withdrawal with the configured KMS-backed hot wallet key.

## Streams

`GET /api/stream?topic=market:NENO-USDC:trades`

Replays Redis stream events for a topic.

WebSocket:

```json
{ "op": "subscribe", "topic": "market:NENO-USDC:book" }
```

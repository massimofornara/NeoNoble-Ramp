# NeoNoble Execution Closure Loop

## Scope

This report documents the production execution loop for treasury-backed settlement without fabricated tx hashes, settlement IDs, provider references, or balances.

## Lifecycle

```text
routing_active
-> execution_attempted
-> settlement_source_ready | liquidity_bootstrap_active | awaiting_real_liquidity
-> execution_successful
-> settlement_pending
-> settlement_confirmed
-> finalized
```

Final balances are recognized only after chain receipts or provider webhooks/proofs.

## Liquidity Bootstrap Layer

The bootstrap layer builds a unified execution pool from:

- BSC hot wallet balances and RPC proof.
- Stripe available balances and payout capability.
- Wise production balances and payout capability.
- Optional external USDT and EUR funding adapters.

The bootstrap layer is implemented in `lib/liquidity/bootstrapLayer.cjs`.

## Auto-Funding Orchestrator

When a transaction cannot settle because of a liquidity deficit, the orchestrator:

1. Builds a bootstrap plan from the current liquidity plan.
2. Checks whether a real funding adapter is configured.
3. Sends an idempotent funding request to the configured provider.
4. Requires a real `fundingRequestId`, `providerReference`, `txHash`, `settlementId`, or `id` in the provider response.
5. Resynchronizes liquidity before allowing the next execution attempt.

Required runtime flags:

```text
LIQUIDITY_BOOTSTRAP_ENABLED=true
LIQUIDITY_BOOTSTRAP_API_URL=<provider endpoint>
LIQUIDITY_BOOTSTRAP_API_KEY=<provider api key>
```

Per-asset overrides are supported:

```text
USDT_FUNDING_REQUEST_URL
USDT_LIQUIDITY_PROVIDER_URL
USDT_LIQUIDITY_PROVIDER_API_KEY
EUR_FUNDING_REQUEST_URL
EUR_LIQUIDITY_PROVIDER_URL
EUR_LIQUIDITY_PROVIDER_API_KEY
```

## Settlement Gate Resolver

The settlement gate is implemented in `lib/settlement/settlementGateResolver.cjs`.

Gate behavior:

- Opens when a real chain/provider settlement source can allocate the required amount.
- Waits when a funding request has been accepted by a real provider.
- Blocks only when no funded source and no configured bootstrap adapter can satisfy the settlement.

Gate decisions are persisted through `TransactionEvent` records:

- `liquidity.bootstrap_planned`
- `liquidity.bootstrap_requested`
- `liquidity.bootstrap_failed`
- `settlement.gate_open`
- `settlement.gate_waiting_funding`
- `settlement.gate_blocked`

## Worker Behavior

The transaction worker now treats `awaiting_real_liquidity`, `liquidity_bootstrap_active`, and `settlement_source_ready` as active closure-loop states.

On each retry cycle it:

1. Resynchronizes provider/chain balances.
2. Runs bootstrap if no settlement source is funded.
3. Re-enters execution automatically if the gate opens.
4. Emits `execution.successful` only after a real broadcast/provider action.
5. Finalizes only from chain receipt finality or provider settlement webhook.

## Current Target State

The current target transactions are structurally ready, but blocked by live liquidity:

- Swap requires `240000 USDT` on BSC hot wallet and real blockchain execution mode.
- Off-ramp requires `2,000,000 EUR` in Stripe/Wise or a configured EUR funding adapter plus Wise recipient/beneficiary details.

No artificial settlement proof is accepted by this loop.

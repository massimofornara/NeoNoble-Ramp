import { ensureAccount, postLedgerTransaction } from '@/lib/exchange/ledger';
import { quoteSwap } from '@/lib/exchange/pricingEngine';
import { evaluateSwapRisk } from '@/lib/exchange/riskEngine';
import { query, withPgTransaction } from '@/lib/exchange/db';
import { publishEvent } from '@/lib/exchange/eventBus';
import { exchangeSettlementLatency, exchangeSwapCounter } from '@/lib/transak/metrics';
import type { SwapRequest } from '@/types/exchange';

export async function executeSwap(request: SwapRequest) {
  const timer = exchangeSettlementLatency.startTimer();
  const risk = await evaluateSwapRisk(request);
  if (!risk.allowed) {
    exchangeSwapCounter.inc({ from_asset: request.fromAsset, to_asset: request.toAsset, result: 'risk_blocked' });
    throw new Error(`Risk blocked swap: ${risk.reasons.join(',')}`);
  }

  const quote = await quoteSwap({
    fromAsset: request.fromAsset,
    toAsset: request.toAsset,
    amountIn: request.amount,
    maxSlippageBps: request.maxSlippageBps,
  });

  const userFrom = await ensureAccount({
    ownerId: request.userId,
    accountType: 'USER',
    asset: request.fromAsset,
    normalBalance: 'CREDIT',
  });
  const userTo = await ensureAccount({
    ownerId: request.userId,
    accountType: 'USER',
    asset: request.toAsset,
    normalBalance: 'CREDIT',
  });
  const poolFrom = await ensureAccount({
    accountType: 'LIQUIDITY_POOL',
    asset: request.fromAsset,
    normalBalance: 'CREDIT',
    allowOverdraft: true,
  });
  const poolTo = await ensureAccount({
    accountType: 'LIQUIDITY_POOL',
    asset: request.toAsset,
    normalBalance: 'CREDIT',
    allowOverdraft: true,
  });

  const order = await withPgTransaction(async (client) => {
    const existing = await client.query<{ id: string; ledger_transaction_id: string | null }>(
      'select id, ledger_transaction_id from exchange_orders where idempotency_key = $1',
      [request.idempotencyKey],
    );
    if (existing.rows[0]) return existing.rows[0];

    const created = await client.query<{ id: string }>(
      `insert into exchange_orders
        (user_id, order_type, side, base_asset, quote_asset, amount, limit_price, max_slippage_bps, idempotency_key, correlation_id)
       values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
       returning id`,
      [
        request.userId,
        request.orderType,
        request.side || 'SELL',
        request.fromAsset,
        request.toAsset,
        request.amount,
        request.limitPrice || null,
        request.maxSlippageBps || 100,
        request.idempotencyKey,
        request.correlationId,
      ],
    );
    return { id: created.rows[0].id, ledger_transaction_id: null };
  });

  if (order.ledger_transaction_id) {
    const rows = await query('select * from swap_executions where order_id = $1 limit 1', [order.id]);
    return { orderId: order.id, quote, execution: rows[0] || null, idempotent: true };
  }

  const ledger = await postLedgerTransaction({
    idempotencyKey: `ledger:${request.idempotencyKey}`,
    correlationId: request.correlationId,
    transactionType: 'SWAP_EXECUTION',
    entries: [
      { accountId: userFrom, asset: request.fromAsset, direction: 'DEBIT', amount: request.amount, memo: 'User pays swap input' },
      { accountId: poolFrom, asset: request.fromAsset, direction: 'CREDIT', amount: request.amount, memo: 'Pool receives swap input' },
      { accountId: poolTo, asset: request.toAsset, direction: 'DEBIT', amount: quote.amountOut, memo: 'Pool pays swap output' },
      { accountId: userTo, asset: request.toAsset, direction: 'CREDIT', amount: quote.amountOut, memo: 'User receives swap output' },
    ],
    metadata: { orderId: order.id, quote },
  });

  const execution = await withPgTransaction(async (client) => {
    await client.query(
      "update exchange_orders set state = 'SETTLED', ledger_transaction_id = $2, updated_at = now() where id = $1",
      [order.id, ledger.id],
    );
    const result = await client.query<{ id: string }>(
      `insert into swap_executions
        (order_id, user_id, from_asset, to_asset, amount_in, amount_out, execution_price, spread_bps, slippage_bps, route, ledger_transaction_id)
       values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
       returning id`,
      [
        order.id,
        request.userId,
        request.fromAsset,
        request.toAsset,
        request.amount,
        quote.amountOut,
        quote.price,
        quote.spreadBps,
        quote.slippageBps,
        JSON.stringify(quote.route),
        ledger.id,
      ],
    );
    return result.rows[0];
  });

  await publishEvent({
    type: 'SwapExecuted',
    aggregateId: order.id,
    correlationId: request.correlationId,
    payload: { ledgerTransactionId: ledger.id, executionId: execution.id, quote },
  });

  timer();
  exchangeSwapCounter.inc({ from_asset: request.fromAsset, to_asset: request.toAsset, result: 'settled' });
  return { orderId: order.id, ledgerTransactionId: ledger.id, executionId: execution.id, quote, risk };
}

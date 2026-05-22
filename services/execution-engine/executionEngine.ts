import { query, withPgTransaction, writeQuery } from '@/lib/exchange/db';
import { ensureAccount, postLedgerTransaction } from '@/lib/exchange/ledger';
import { add, compare, multiplyDecimal, subtract } from '@/lib/exchange/money';
import { matchOrder, type RestingOrder } from '@/lib/matching-engine/matchingEngine';
import { publishEvent } from '@/lib/exchange/eventBus';
import type { ClobOrderRequest, MatchFill } from '@/types/tier1';

type MarketRow = {
  market: string;
  base_asset: string;
  quote_asset: string;
  maker_fee_bps: number;
  taker_fee_bps: number;
  status: string;
};

function nextState(quantity: string, remaining: string) {
  if (compare(remaining, '0') === 0) return 'FILLED';
  if (compare(remaining, quantity) < 0) return 'PARTIALLY_FILLED';
  return 'OPEN';
}

async function settleFill(fill: MatchFill, market: MarketRow, takerSide: 'BUY' | 'SELL', correlationId: string) {
  const buyerUserId = takerSide === 'BUY' ? fill.takerUserId : fill.makerUserId;
  const sellerUserId = takerSide === 'SELL' ? fill.takerUserId : fill.makerUserId;
  const buyerFee = takerSide === 'BUY' ? fill.takerFee : fill.makerFee;
  const sellerFee = takerSide === 'SELL' ? fill.takerFee : fill.makerFee;
  const notional = multiplyDecimal(fill.quantity, fill.price);

  const buyerBase = await ensureAccount({ ownerId: buyerUserId, accountType: 'USER', asset: market.base_asset, normalBalance: 'CREDIT' });
  const sellerBase = await ensureAccount({ ownerId: sellerUserId, accountType: 'USER', asset: market.base_asset, normalBalance: 'CREDIT' });
  const buyerQuote = await ensureAccount({ ownerId: buyerUserId, accountType: 'USER', asset: market.quote_asset, normalBalance: 'CREDIT' });
  const sellerQuote = await ensureAccount({ ownerId: sellerUserId, accountType: 'USER', asset: market.quote_asset, normalBalance: 'CREDIT' });
  const feeQuote = await ensureAccount({ accountType: 'FEE_REVENUE', asset: market.quote_asset, normalBalance: 'CREDIT', allowOverdraft: true });

  const ledger = await postLedgerTransaction({
    idempotencyKey: `trade:${fill.takerOrderId}:${fill.makerOrderId}:${fill.quantity}:${fill.price}`,
    correlationId,
    transactionType: 'CLOB_TRADE_SETTLEMENT',
    entries: [
      { accountId: sellerBase, asset: market.base_asset, direction: 'DEBIT', amount: fill.quantity, memo: 'Seller delivers base asset' },
      { accountId: buyerBase, asset: market.base_asset, direction: 'CREDIT', amount: fill.quantity, memo: 'Buyer receives base asset' },
      { accountId: buyerQuote, asset: market.quote_asset, direction: 'DEBIT', amount: add(notional, buyerFee), memo: 'Buyer pays quote and fee' },
      { accountId: sellerQuote, asset: market.quote_asset, direction: 'CREDIT', amount: subtract(notional, sellerFee), memo: 'Seller receives quote net fee' },
      { accountId: feeQuote, asset: market.quote_asset, direction: 'CREDIT', amount: add(buyerFee, sellerFee), memo: 'Exchange trading fees' },
    ],
    metadata: { fill, market: market.market },
  });

  return ledger.id;
}

export async function placeClobOrder(request: ClobOrderRequest) {
  const market = (await query<MarketRow>('select * from clob_markets where market = $1', [request.market]))[0];
  if (!market || market.status !== 'ONLINE') throw new Error('Market is not available');
  if (request.type !== 'MARKET' && !request.price) throw new Error('LIMIT and STOP orders require price');

  const created = await withPgTransaction(async (client) => {
    await client.query('select pg_advisory_xact_lock(hashtext($1))', [request.market]);
    const existing = await client.query<{ id: string }>('select id::text from clob_orders where idempotency_key = $1', [request.idempotencyKey]);
    if (existing.rows[0]) return { id: existing.rows[0].id, idempotent: true };
    const row = await client.query<{ id: string }>(
      `insert into clob_orders
        (user_id, market, side, order_type, order_state, quantity, remaining_quantity, price, stop_price, time_in_force, idempotency_key, correlation_id)
       values ($1, $2, $3, $4, 'CREATED', $5, $5, $6, $7, $8, $9, $10)
       returning id::text`,
      [
        request.userId,
        request.market,
        request.side,
        request.type,
        request.quantity,
        request.price || null,
        request.stopPrice || null,
        request.timeInForce || 'GTC',
        request.idempotencyKey,
        request.correlationId,
      ],
    );
    await client.query("update clob_orders set order_state = 'OPEN', updated_at = now() where id = $1", [row.rows[0].id]);
    return { id: row.rows[0].id, idempotent: false };
  });

  if (created.idempotent) return { orderId: created.id, idempotent: true, fills: [] };

  const resting = await query<RestingOrder>(
    `select id::text, user_id as "userId", side::text as side, price::text, remaining_quantity::text as "remainingQuantity", sequence::int
     from clob_orders
     where market = $1
       and side <> $2
       and order_state in ('OPEN', 'PARTIALLY_FILLED')
       and id <> $3
       and price is not null
     order by
       case when $2 = 'BUY' then price end asc,
       case when $2 = 'SELL' then price end desc,
       sequence asc
     limit 100`,
    [request.market, request.side, created.id],
  );

  const matched = matchOrder({
    takerOrderId: created.id,
    taker: request,
    resting,
    makerFeeBps: market.maker_fee_bps,
    takerFeeBps: market.taker_fee_bps,
  });

  const fills: MatchFill[] = [];
  for (const fill of matched.fills) {
    const ledgerTransactionId = await settleFill(fill, market, request.side, request.correlationId);
    const trade = await writeQuery<{ id: string }>(
      `insert into clob_trades
        (market, maker_order_id, taker_order_id, maker_user_id, taker_user_id, price, quantity, maker_fee, taker_fee, ledger_transaction_id)
       values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
       returning id::text`,
      [
        request.market,
        fill.makerOrderId,
        fill.takerOrderId,
        fill.makerUserId,
        fill.takerUserId,
        fill.price,
        fill.quantity,
        fill.makerFee,
        fill.takerFee,
        ledgerTransactionId,
      ],
    );
    fill.tradeId = trade[0].id;
    fills.push(fill);
    await writeQuery(
      `update clob_orders
       set remaining_quantity = remaining_quantity - $2::numeric,
           order_state = case when remaining_quantity - $2::numeric = 0 then 'FILLED'::clob_order_state else 'PARTIALLY_FILLED'::clob_order_state end,
           updated_at = now()
       where id = $1`,
      [fill.makerOrderId, fill.quantity],
    );
  }

  await writeQuery('update clob_orders set remaining_quantity = $2, order_state = $3, updated_at = now() where id = $1', [
    created.id,
    matched.remainingQuantity,
    request.timeInForce === 'IOC' && compare(matched.remainingQuantity, '0') > 0 ? 'CANCELLED' : nextState(request.quantity, matched.remainingQuantity),
  ]);

  await publishEvent({
    type: 'SwapExecuted',
    aggregateId: created.id,
    correlationId: request.correlationId,
    payload: { market: request.market, fills: fills.length, orderModel: 'CLOB' },
  });

  return { orderId: created.id, fills, remainingQuantity: matched.remainingQuantity };
}

export async function cancelClobOrder(orderId: string, userId: string) {
  const row = await writeQuery<{ id: string }>(
    `update clob_orders
     set order_state = 'CANCELLED', updated_at = now()
     where id = $1 and user_id = $2 and order_state in ('OPEN', 'PARTIALLY_FILLED')
     returning id::text`,
    [orderId, userId],
  );
  if (!row[0]) throw new Error('Order not cancellable');
  return { orderId };
}

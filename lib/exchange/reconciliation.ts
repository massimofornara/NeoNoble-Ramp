import { query, withPgTransaction } from '@/lib/exchange/db';
import { ensureAccount, postLedgerTransaction } from '@/lib/exchange/ledger';
import { publishEvent } from '@/lib/exchange/eventBus';
import { log } from '@/lib/transak/logger';
import type { TransakOrder } from '@/types/transak';

function getTransakOrder(payload: Record<string, unknown>): TransakOrder | null {
  const decoded = payload.decoded_payload as { webhookData?: TransakOrder } | null;
  return decoded?.webhookData || null;
}

export async function reconcileTransakCompletedOrders(limit = 100) {
  const events = await query<{ event_id: string; decoded_payload: Record<string, unknown> }>(
    `select event_id, decoded_payload
     from webhook_events
     where provider = 'transak'
       and processed = true
       and decoded_payload is not null
     order by created_at desc
     limit $1`,
    [limit],
  );

  const report = {
    scanned: events.length,
    posted: 0,
    skipped: 0,
    mismatches: [] as string[],
  };

  for (const event of events) {
    const order = getTransakOrder(event as unknown as Record<string, unknown>);
    if (!order || order.status !== 'COMPLETED') {
      report.skipped += 1;
      continue;
    }

    const orderId = order.id || order.orderId || event.event_id;
    const existing = await query('select id from ledger_transactions where external_provider = $1 and external_id = $2', ['transak', orderId]);
    if (existing[0]) {
      report.skipped += 1;
      continue;
    }

    const userId = order.partnerCustomerId || order.walletAddress || 'unknown-transak-user';
    const asset = order.cryptoCurrency || 'NENO';
    const amount = order.cryptoAmount ? String(order.cryptoAmount) : '0';
    if (amount === '0') {
      report.mismatches.push(`Missing crypto amount for ${orderId}`);
      continue;
    }

    const userAccount = await ensureAccount({ ownerId: userId, accountType: 'USER', asset, normalBalance: 'CREDIT' });
    const reserveAccount = await ensureAccount({ accountType: 'EXCHANGE_RESERVE', asset, normalBalance: 'CREDIT', allowOverdraft: true });

    await postLedgerTransaction({
      idempotencyKey: `transak:${orderId}`,
      correlationId: order.partnerOrderId || orderId,
      transactionType: 'FIAT_RAIL_SETTLEMENT',
      externalProvider: 'transak',
      externalId: orderId,
      entries: [
        { accountId: reserveAccount, asset, direction: 'DEBIT', amount, memo: 'Transak reserve source' },
        { accountId: userAccount, asset, direction: 'CREDIT', amount, memo: 'User credited from Transak on-ramp' },
      ],
      metadata: { order },
    });

    await publishEvent({
      type: 'FiatDepositConfirmed',
      aggregateId: orderId,
      correlationId: order.partnerOrderId || orderId,
      payload: { userId, asset, amount },
    });
    report.posted += 1;
  }

  log.info('transak_reconciliation_completed', report);
  return report;
}

export async function markStaleTransactionsFailed() {
  return withPgTransaction(async (client) => {
    const result = await client.query(
      `update ledger_transactions
       set state = 'FAILED', updated_at = now()
       where state in ('CREATED', 'PENDING', 'PROCESSING')
         and created_at < now() - interval '24 hours'
       returning id::text`,
    );
    for (const row of result.rows as Array<{ id: string }>) {
      await client.query(
        `insert into transaction_events(ledger_transaction_id, aggregate_id, event_type, previous_state, next_state, correlation_id, payload)
         values ($1, $1::text, 'TransactionAutoFailed', 'PROCESSING', 'FAILED', $1::text, '{}')`,
        [row.id],
      );
    }
    return { failed: result.rowCount || 0 };
  });
}

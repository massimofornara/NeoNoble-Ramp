import type { PoolClient } from 'pg';
import type { AccountType, LedgerEntryInput, LedgerTransactionInput, LedgerTransactionResult, NormalBalance } from '@/types/exchange';
import { compare, toAtomic } from '@/lib/exchange/money';
import { withPgTransaction } from '@/lib/exchange/db';
import { appendAuditLog } from '@/lib/exchange/audit';
import { publishEvent } from '@/lib/exchange/eventBus';
import { transitionLedgerTransaction } from '@/lib/exchange/stateMachine';

function assertBalanced(entries: LedgerEntryInput[]) {
  const byAsset = new Map<string, { debit: bigint; credit: bigint }>();
  for (const entry of entries) {
    if (toAtomic(entry.amount) <= 0n) throw new Error('Journal entry amount must be positive');
    const current = byAsset.get(entry.asset) || { debit: 0n, credit: 0n };
    if (entry.direction === 'DEBIT') current.debit += toAtomic(entry.amount);
    else current.credit += toAtomic(entry.amount);
    byAsset.set(entry.asset, current);
  }

  for (const [asset, value] of byAsset.entries()) {
    if (value.debit !== value.credit) {
      throw new Error(`Unbalanced journal for ${asset}: debit ${value.debit} credit ${value.credit}`);
    }
  }
}

async function applyEntry(client: PoolClient, entry: LedgerEntryInput) {
  const account = await client.query<{ normal_balance: NormalBalance; allow_overdraft: boolean }>(
    'select normal_balance, allow_overdraft from accounts where id = $1 and status = $2 for update',
    [entry.accountId, 'ACTIVE'],
  );
  if (!account.rows[0]) throw new Error(`Account not found or inactive: ${entry.accountId}`);

  await client.query(
    `insert into balances(account_id, asset, available, held)
     values ($1, $2, 0, 0)
     on conflict (account_id, asset) do nothing`,
    [entry.accountId, entry.asset],
  );

  const increases = account.rows[0].normal_balance === entry.direction;
  const delta = increases ? entry.amount : `-${entry.amount}`;
  const updated = await client.query<{ available: string }>(
    `update balances
       set available = available + $3::numeric,
           version = version + 1,
           updated_at = now()
     where account_id = $1 and asset = $2
     returning available::text`,
    [entry.accountId, entry.asset, delta],
  );

  if (!account.rows[0].allow_overdraft && compare(updated.rows[0].available, '0') < 0) {
    throw new Error(`Insufficient funds for account ${entry.accountId} ${entry.asset}`);
  }
}

export async function ensureAccount(input: {
  ownerId?: string;
  accountType: AccountType;
  asset: string;
  normalBalance: NormalBalance;
  allowOverdraft?: boolean;
  metadata?: Record<string, unknown>;
}) {
  return withPgTransaction(async (client) => {
    const existing = await client.query<{ id: string }>(
      `select id from accounts
       where coalesce(owner_id, 'SYSTEM') = coalesce($1, 'SYSTEM')
         and account_type = $2
         and asset = $3
       for update`,
      [input.ownerId || null, input.accountType, input.asset],
    );
    if (existing.rows[0]) return existing.rows[0].id;

    const result = await client.query<{ id: string }>(
      `insert into accounts(owner_id, account_type, asset, normal_balance, allow_overdraft, metadata)
       values ($1, $2, $3, $4, $5, $6)
       returning id`,
      [
        input.ownerId || null,
        input.accountType,
        input.asset,
        input.normalBalance,
        Boolean(input.allowOverdraft),
        JSON.stringify(input.metadata || {}),
      ],
    );
    await client.query(
      `insert into balances(account_id, asset, available, held)
       values ($1, $2, 0, 0)
       on conflict (account_id, asset) do nothing`,
      [result.rows[0].id, input.asset],
    );
    return result.rows[0].id;
  });
}

export async function postLedgerTransaction(input: LedgerTransactionInput): Promise<LedgerTransactionResult> {
  assertBalanced(input.entries);

  const result = await withPgTransaction(async (client) => {
    const existing = await client.query<{ id: string; state: LedgerTransactionResult['state'] }>(
      'select id, state from ledger_transactions where idempotency_key = $1',
      [input.idempotencyKey],
    );
    if (existing.rows[0]) {
      return {
        id: existing.rows[0].id,
        idempotencyKey: input.idempotencyKey,
        state: existing.rows[0].state,
        journalEntryCount: input.entries.length,
      };
    }

    const tx = await client.query<{ id: string }>(
      `insert into ledger_transactions
        (idempotency_key, correlation_id, transaction_type, state, external_provider, external_id, metadata)
       values ($1, $2, $3, 'CREATED', $4, $5, $6)
       returning id`,
      [
        input.idempotencyKey,
        input.correlationId,
        input.transactionType,
        input.externalProvider || null,
        input.externalId || null,
        JSON.stringify(input.metadata || {}),
      ],
    );

    await transitionLedgerTransaction(client, {
      ledgerTransactionId: tx.rows[0].id,
      aggregateId: tx.rows[0].id,
      nextState: 'PENDING',
      correlationId: input.correlationId,
      eventType: 'TransactionCreated',
      payload: { transactionType: input.transactionType },
    });

    for (const [index, entry] of input.entries.entries()) {
      await applyEntry(client, entry);
      await client.query(
        `insert into journal_entries
          (ledger_transaction_id, account_id, asset, direction, amount, entry_index, memo, metadata)
         values ($1, $2, $3, $4, $5, $6, $7, $8)`,
        [
          tx.rows[0].id,
          entry.accountId,
          entry.asset,
          entry.direction,
          entry.amount,
          index,
          entry.memo || null,
          JSON.stringify(entry.metadata || {}),
        ],
      );
    }

    await transitionLedgerTransaction(client, {
      ledgerTransactionId: tx.rows[0].id,
      aggregateId: tx.rows[0].id,
      nextState: 'PROCESSING',
      correlationId: input.correlationId,
      eventType: 'JournalEntriesCommitted',
      payload: { entries: input.entries.length },
    });

    await transitionLedgerTransaction(client, {
      ledgerTransactionId: tx.rows[0].id,
      aggregateId: tx.rows[0].id,
      nextState: 'SETTLED',
      correlationId: input.correlationId,
      eventType: 'LedgerUpdated',
      payload: { entries: input.entries.length },
    });

    await appendAuditLog(client, {
      action: 'LEDGER_TRANSACTION_POSTED',
      resourceType: 'ledger_transaction',
      resourceId: tx.rows[0].id,
      correlationId: input.correlationId,
      payload: { idempotencyKey: input.idempotencyKey, entries: input.entries.length },
    });

    return {
      id: tx.rows[0].id,
      idempotencyKey: input.idempotencyKey,
      state: 'SETTLED' as const,
      journalEntryCount: input.entries.length,
    };
  });

  await publishEvent({
    type: 'LedgerUpdated',
    aggregateId: result.id,
    correlationId: input.correlationId,
    payload: { transactionType: input.transactionType, entries: input.entries.length },
  });

  return result;
}

export async function placeHold(input: {
  accountId: string;
  asset: string;
  amount: string;
  reason: string;
  idempotencyKey: string;
  correlationId: string;
  metadata?: Record<string, unknown>;
}) {
  return withPgTransaction(async (client) => {
    const existing = await client.query<{ id: string }>('select id from holds where idempotency_key = $1', [input.idempotencyKey]);
    if (existing.rows[0]) return existing.rows[0].id;

    const updated = await client.query<{ available: string }>(
      `update balances
         set available = available - $3::numeric,
             held = held + $3::numeric,
             version = version + 1,
             updated_at = now()
       where account_id = $1 and asset = $2
       returning available::text`,
      [input.accountId, input.asset, input.amount],
    );
    if (!updated.rows[0] || compare(updated.rows[0].available, '0') < 0) {
      throw new Error('Insufficient available balance for hold');
    }

    const hold = await client.query<{ id: string }>(
      `insert into holds(account_id, asset, amount, reason, idempotency_key, correlation_id, metadata)
       values ($1, $2, $3, $4, $5, $6, $7)
       returning id`,
      [
        input.accountId,
        input.asset,
        input.amount,
        input.reason,
        input.idempotencyKey,
        input.correlationId,
        JSON.stringify(input.metadata || {}),
      ],
    );
    return hold.rows[0].id;
  });
}

export async function releaseHold(input: { holdId: string; correlationId: string }) {
  return withPgTransaction(async (client) => {
    const hold = await client.query<{ account_id: string; asset: string; amount: string; status: string }>(
      'select account_id, asset, amount::text, status from holds where id = $1 for update',
      [input.holdId],
    );
    if (!hold.rows[0]) throw new Error('Hold not found');
    if (hold.rows[0].status !== 'ACTIVE') return false;
    await client.query(
      `update balances
         set available = available + $3::numeric,
             held = held - $3::numeric,
             version = version + 1,
             updated_at = now()
       where account_id = $1 and asset = $2`,
      [hold.rows[0].account_id, hold.rows[0].asset, hold.rows[0].amount],
    );
    await client.query("update holds set status = 'RELEASED', released_at = now(), updated_at = now() where id = $1", [input.holdId]);
    return true;
  });
}

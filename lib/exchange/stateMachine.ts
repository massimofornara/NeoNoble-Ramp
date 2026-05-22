import type { PoolClient } from 'pg';
import type { TransactionState } from '@/types/exchange';

const allowed: Record<TransactionState, TransactionState[]> = {
  CREATED: ['PENDING', 'FAILED'],
  PENDING: ['PROCESSING', 'FAILED', 'REVERSED'],
  PROCESSING: ['SETTLED', 'FAILED', 'REVERSED'],
  SETTLED: ['REVERSED'],
  FAILED: [],
  REVERSED: [],
};

export function assertTransition(from: TransactionState, to: TransactionState) {
  if (!allowed[from]?.includes(to)) {
    throw new Error(`Invalid transaction state transition ${from} -> ${to}`);
  }
}

export async function transitionLedgerTransaction(
  client: PoolClient,
  input: {
    ledgerTransactionId: string;
    aggregateId: string;
    nextState: TransactionState;
    correlationId: string;
    eventType: string;
    payload?: Record<string, unknown>;
  },
) {
  const current = await client.query<{ state: TransactionState }>(
    'select state from ledger_transactions where id = $1 for update',
    [input.ledgerTransactionId],
  );
  if (!current.rows[0]) throw new Error('Ledger transaction not found');
  const previousState = current.rows[0].state;
  assertTransition(previousState, input.nextState);

  await client.query(
    'update ledger_transactions set state = $2, updated_at = now() where id = $1',
    [input.ledgerTransactionId, input.nextState],
  );

  await client.query(
    `insert into transaction_events
      (ledger_transaction_id, aggregate_id, event_type, previous_state, next_state, correlation_id, payload)
     values ($1, $2, $3, $4, $5, $6, $7)`,
    [
      input.ledgerTransactionId,
      input.aggregateId,
      input.eventType,
      previousState,
      input.nextState,
      input.correlationId,
      JSON.stringify(input.payload || {}),
    ],
  );
}

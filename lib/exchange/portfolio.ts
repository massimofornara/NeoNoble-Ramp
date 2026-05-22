import { query } from '@/lib/exchange/db';

export async function getPortfolio(userId: string) {
  const balances = await query<{
    account_id: string;
    asset: string;
    available: string;
    held: string;
    account_type: string;
  }>(
    `select b.account_id::text, b.asset, b.available::text, b.held::text, a.account_type::text
     from balances b
     join accounts a on a.id = b.account_id
     where a.owner_id = $1
     order by b.asset`,
    [userId],
  );

  const transactions = await query(
    `select lt.id::text, lt.transaction_type, lt.state::text, lt.metadata, lt.created_at
     from ledger_transactions lt
     where exists (
       select 1
       from journal_entries je
       join accounts a on a.id = je.account_id
       where je.ledger_transaction_id = lt.id and a.owner_id = $1
     )
     order by lt.created_at desc
     limit 50`,
    [userId],
  );

  const risk = await query(
    `select risk_type, severity, score, blocked, payload, created_at
     from risk_events
     where user_id = $1
     order by created_at desc
     limit 20`,
    [userId],
  );

  return { balances, transactions, risk };
}

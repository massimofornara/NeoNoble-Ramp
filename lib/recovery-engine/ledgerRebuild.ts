import { withPgTransaction } from '@/lib/exchange/db';

export async function rebuildBalancesFromJournal() {
  return withPgTransaction(async (client) => {
    await client.query('delete from balances');
    const accounts = await client.query<{ account_id: string; asset: string }>(
      'select distinct account_id::text, asset from journal_entries',
    );
    for (const account of accounts.rows) {
      await client.query(
        `insert into balances(account_id, asset, available, held, version)
         values ($1, $2, 0, 0, 0)
         on conflict(account_id, asset) do nothing`,
        [account.account_id, account.asset],
      );
    }
    await client.query(
      `with deltas as (
        select je.account_id, je.asset,
               sum(case
                 when a.normal_balance::text = je.direction::text then je.amount
                 else -je.amount
               end) as delta
        from journal_entries je
        join accounts a on a.id = je.account_id
        group by je.account_id, je.asset
      )
      update balances b
         set available = d.delta,
             version = version + 1,
             updated_at = now()
      from deltas d
      where b.account_id = d.account_id and b.asset = d.asset`,
    );
    const checkpoint = await client.query<{ id: string }>(
      `insert into recovery_checkpoints(checkpoint_type, payload)
       values ('LEDGER_REBUILD', jsonb_build_object('rebuiltAt', now()))
       returning id::text`,
    );
    return { checkpointId: checkpoint.rows[0].id, accounts: accounts.rowCount || 0 };
  });
}

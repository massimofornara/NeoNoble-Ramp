import { query, writeQuery } from '@/lib/exchange/db';

export async function detectWashTrading(market: string, lookbackMinutes = 10) {
  const rows = await query<{ user_id: string; trades: string }>(
    `select maker_user_id as user_id, count(*)::text as trades
     from clob_trades
     where market = $1 and maker_user_id = taker_user_id and created_at > now() - ($2::text || ' minutes')::interval
     group by maker_user_id`,
    [market, lookbackMinutes],
  );
  for (const row of rows) {
    await writeQuery(
      `insert into compliance_cases(user_id, case_type, severity, score, payload)
       values ($1, 'MARKET_MANIPULATION', 'HIGH', 80, $2)`,
      [row.user_id, JSON.stringify({ market, trades: row.trades, rule: 'self_trade_wash_detection' })],
    );
  }
  return rows;
}

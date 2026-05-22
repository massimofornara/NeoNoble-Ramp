import { query, writeQuery } from '@/lib/exchange/db';
import type { OracleSourcePrice } from '@/types/tier1';

export async function recordOracleSourcePrice(input: {
  baseAsset: string;
  quoteAsset: string;
  source: string;
  price: string;
  weight?: number;
  observedAt?: string;
}) {
  await writeQuery(
    `insert into oracle_source_prices(base_asset, quote_asset, source, price, weight, observed_at)
     values ($1, $2, $3, $4, $5, $6)`,
    [input.baseAsset, input.quoteAsset, input.source, input.price, input.weight || 1, input.observedAt || new Date().toISOString()],
  );
}

export async function aggregateWeightedMedian(baseAsset: string, quoteAsset: string, lookbackSeconds = 60) {
  const rows = await query<OracleSourcePrice>(
    `select source, price::text, weight, observed_at::text as "observedAt"
     from oracle_source_prices
     where base_asset = $1 and quote_asset = $2 and observed_at > now() - ($3::text || ' seconds')::interval
     order by price asc`,
    [baseAsset, quoteAsset, lookbackSeconds],
  );
  if (rows.length === 0) throw new Error(`No oracle prices for ${baseAsset}/${quoteAsset}`);
  const totalWeight = rows.reduce((acc, row) => acc + row.weight, 0);
  let cumulative = 0;
  for (const row of rows) {
    cumulative += row.weight;
    if (cumulative >= totalWeight / 2) {
      await writeQuery(
        `insert into oracle_prices(base_asset, quote_asset, price, source, confidence_bps)
         values ($1, $2, $3, 'weighted_median', $4)`,
        [baseAsset, quoteAsset, row.price, Math.min(10000, rows.length * 2000)],
      );
      return { price: row.price, sourceCount: rows.length, totalWeight };
    }
  }
  return { price: rows[rows.length - 1].price, sourceCount: rows.length, totalWeight };
}

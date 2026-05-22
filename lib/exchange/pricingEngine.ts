import { query } from '@/lib/exchange/db';
import { toAtomic, fromAtomic } from '@/lib/exchange/money';
import type { SwapQuote } from '@/types/exchange';

export async function getOraclePrice(baseAsset: string, quoteAsset: string) {
  const direct = await query<{ price: string; confidence_bps: number }>(
    `select price::text, confidence_bps
     from oracle_prices
     where base_asset = $1 and quote_asset = $2
     order by observed_at desc
     limit 1`,
    [baseAsset, quoteAsset],
  );
  if (direct[0]) return direct[0].price;

  const inverse = await query<{ price: string }>(
    `select price::text
     from oracle_prices
     where base_asset = $2 and quote_asset = $1
     order by observed_at desc
     limit 1`,
    [baseAsset, quoteAsset],
  );
  if (!inverse[0]) throw new Error(`Missing oracle price for ${baseAsset}/${quoteAsset}`);
  return fromAtomic((10n ** 36n) / toAtomic(inverse[0].price));
}

export async function quoteSwap(input: {
  fromAsset: string;
  toAsset: string;
  amountIn: string;
  maxSlippageBps?: number;
}): Promise<SwapQuote> {
  const pool = await query<{ id: string; base_depth: string; quote_depth: string; spread_bps: number }>(
    `select id, base_depth::text, quote_depth::text, spread_bps
     from liquidity_pools
     where enabled = true
       and ((base_asset = $1 and quote_asset = $2) or (base_asset = $2 and quote_asset = $1))
     order by updated_at desc
     limit 1`,
    [input.fromAsset, input.toAsset],
  );
  if (!pool[0]) throw new Error(`No internal liquidity pool for ${input.fromAsset}/${input.toAsset}`);

  const price = await getOraclePrice(input.fromAsset, input.toAsset);
  const spreadAmount = (toAtomic(input.amountIn) * BigInt(pool[0].spread_bps)) / 10_000n;
  const netAmountIn = toAtomic(input.amountIn) - spreadAmount;
  const rawOut = (netAmountIn * toAtomic(price)) / (10n ** 18n);
  const depth = toAtomic(pool[0].quote_depth || '0');
  const slippageBps = depth > 0n ? Number((rawOut * 10_000n) / depth) : 10_000;
  const maxSlippage = input.maxSlippageBps ?? 100;
  if (slippageBps > maxSlippage) {
    throw new Error(`Slippage ${slippageBps}bps exceeds max ${maxSlippage}bps`);
  }

  return {
    fromAsset: input.fromAsset,
    toAsset: input.toAsset,
    amountIn: input.amountIn,
    amountOut: fromAtomic(rawOut),
    price,
    spreadBps: pool[0].spread_bps,
    slippageBps,
    route: [{ poolId: pool[0].id, fromAsset: input.fromAsset, toAsset: input.toAsset, depth: pool[0].quote_depth }],
  };
}

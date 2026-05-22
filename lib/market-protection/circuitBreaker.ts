import { compare } from '@/lib/exchange/money';
import { query, writeQuery } from '@/lib/exchange/db';

function absBpsMove(reference: string, current: string) {
  const ref = Number(reference);
  const cur = Number(current);
  if (!Number.isFinite(ref) || ref <= 0) return 0;
  return Math.round(Math.abs((cur - ref) / ref) * 10000);
}

export async function evaluateCircuitBreaker(input: {
  market: string;
  currentPrice: string;
  thresholdBps?: number;
}) {
  const breaker = (await query<{ last_reference_price: string | null; state: string }>(
    'select last_reference_price::text, state from market_circuit_breakers where market = $1',
    [input.market],
  ))[0];
  const threshold = input.thresholdBps || Number(process.env.CIRCUIT_BREAKER_FLASH_CRASH_BPS || 1500);
  const reference = breaker?.last_reference_price || input.currentPrice;
  const moveBps = absBpsMove(reference, input.currentPrice);
  const state = moveBps >= threshold ? 'HALTED' : 'OPEN';
  await writeQuery(
    `insert into market_circuit_breakers(market, state, reason, volatility_bps, last_reference_price)
     values ($1, $2, $3, $4, $5)
     on conflict(market) do update set state = excluded.state, reason = excluded.reason, volatility_bps = excluded.volatility_bps, updated_at = now()`,
    [input.market, state, state === 'HALTED' ? 'flash_crash_or_spike' : null, moveBps, reference],
  );
  return { market: input.market, state, moveBps, threshold, halted: state === 'HALTED' };
}

export async function assertMarketOpen(market: string) {
  const breaker = (await query<{ state: string }>('select state from market_circuit_breakers where market = $1', [market]))[0];
  if (breaker?.state === 'HALTED') throw new Error(`Market ${market} is halted by circuit breaker`);
}

import { query, writeQuery } from '@/lib/exchange/db';
import { publishEvent } from '@/lib/exchange/eventBus';
import { riskEventCounter } from '@/lib/transak/metrics';
import type { RiskDecision, SwapRequest } from '@/types/exchange';

const HIGH_RISK_WALLETS = new Set(
  (process.env.RISK_BLOCKED_WALLETS || '')
    .split(',')
    .map((wallet) => wallet.trim().toLowerCase())
    .filter(Boolean),
);

function severity(score: number): RiskDecision['severity'] {
  if (score >= 90) return 'CRITICAL';
  if (score >= 70) return 'HIGH';
  if (score >= 40) return 'MEDIUM';
  return 'LOW';
}

export async function evaluateSwapRisk(request: SwapRequest): Promise<RiskDecision> {
  const reasons: string[] = [];
  let score = 0;

  const rows = await query<{ hour_count: string; day_count: string; hour_volume: string; day_volume: string }>(
    `select
       count(*) filter (where created_at > now() - interval '1 hour')::text as hour_count,
       count(*) filter (where created_at > now() - interval '1 day')::text as day_count,
       coalesce(sum(amount_in) filter (where created_at > now() - interval '1 hour'), 0)::text as hour_volume,
       coalesce(sum(amount_in) filter (where created_at > now() - interval '1 day'), 0)::text as day_volume
     from swap_executions
     where user_id = $1`,
    [request.userId],
  );

  const hourCount = Number(rows[0]?.hour_count || 0);
  const dayCount = Number(rows[0]?.day_count || 0);
  const maxHourlySwaps = Number(process.env.RISK_MAX_HOURLY_SWAPS || 20);
  const maxDailySwaps = Number(process.env.RISK_MAX_DAILY_SWAPS || 100);

  if (hourCount >= maxHourlySwaps) {
    score += 45;
    reasons.push('velocity_hourly_swap_limit');
  }
  if (dayCount >= maxDailySwaps) {
    score += 35;
    reasons.push('velocity_daily_swap_limit');
  }
  if (request.walletAddress && HIGH_RISK_WALLETS.has(request.walletAddress.toLowerCase())) {
    score += 100;
    reasons.push('blocked_wallet');
  }
  if (request.maxSlippageBps && request.maxSlippageBps > 1000) {
    score += 20;
    reasons.push('high_slippage_tolerance');
  }

  const decision = {
    allowed: score < Number(process.env.RISK_BLOCK_SCORE || 70),
    score,
    reasons,
    severity: severity(score),
  };

  if (!decision.allowed) {
    riskEventCounter.inc({ risk_type: 'SWAP_RISK', severity: decision.severity, blocked: 'true' });
    await writeQuery(
      `insert into risk_events(user_id, wallet_address, risk_type, severity, score, blocked, correlation_id, payload)
       values ($1, $2, 'SWAP_RISK', $3, $4, true, $5, $6)`,
      [
        request.userId,
        request.walletAddress || null,
        decision.severity,
        decision.score,
        request.correlationId,
        JSON.stringify({ reasons, request }),
      ],
    );

    await publishEvent({
      type: 'RiskFlagTriggered',
      aggregateId: request.userId,
      correlationId: request.correlationId,
      payload: { score, reasons, blocked: true },
    });
  }

  return decision;
}

export async function evaluateFiatRailRisk(input: {
  userId?: string;
  walletAddress?: string;
  fiatAmount?: number;
  direction: 'DEPOSIT' | 'WITHDRAW';
  correlationId: string;
}) {
  let score = 0;
  const reasons: string[] = [];
  const maxFiat = Number(process.env.RISK_MAX_FIAT_SINGLE_FLOW || 50_000);
  if ((input.fiatAmount || 0) > maxFiat) {
    score += 60;
    reasons.push('large_fiat_flow');
  }
  if (input.walletAddress && HIGH_RISK_WALLETS.has(input.walletAddress.toLowerCase())) {
    score += 100;
    reasons.push('blocked_wallet');
  }
  const decision = { allowed: score < 70, score, reasons, severity: severity(score) };
  if (!decision.allowed) {
    riskEventCounter.inc({ risk_type: 'FIAT_RAIL_RISK', severity: decision.severity, blocked: 'true' });
    await writeQuery(
      `insert into risk_events(user_id, wallet_address, risk_type, severity, score, blocked, correlation_id, payload)
       values ($1, $2, 'FIAT_RAIL_RISK', $3, $4, true, $5, $6)`,
      [
        input.userId || null,
        input.walletAddress || null,
        decision.severity,
        decision.score,
        input.correlationId,
        JSON.stringify({ reasons, input }),
      ],
    );
  }
  return decision;
}

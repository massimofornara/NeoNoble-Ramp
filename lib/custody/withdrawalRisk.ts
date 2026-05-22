import { compare } from '@/lib/exchange/money';
import { evaluateFiatRailRisk } from '@/lib/exchange/riskEngine';
import { query } from '@/lib/exchange/db';
import type { ComplianceDecision, CustodyWithdrawalRequest } from '@/types/tier1';

export async function scoreWithdrawalRisk(input: CustodyWithdrawalRequest): Promise<ComplianceDecision> {
  const reasons: string[] = [];
  let score = 0;
  const sanctions = await query<{ severity: string }>(
    'select severity from sanctions_entities where active = true and lower(value) = lower($1) limit 1',
    [input.destinationAddress],
  );
  if (sanctions[0]) {
    score += sanctions[0].severity === 'CRITICAL' ? 100 : 80;
    reasons.push('sanctions_or_blacklist_match');
  }

  const cluster = await query<{ risk_score: number; labels: string[] }>(
    'select risk_score, labels from wallet_clusters where lower(address) = lower($1) limit 1',
    [input.destinationAddress],
  );
  if (cluster[0]?.risk_score) {
    score += cluster[0].risk_score;
    reasons.push('wallet_cluster_risk');
  }

  const large = compare(input.amount, process.env.WITHDRAWAL_LARGE_AMOUNT_THRESHOLD || '100000') > 0;
  if (large) {
    score += 30;
    reasons.push('large_withdrawal');
  }

  const railRisk = await evaluateFiatRailRisk({
    userId: input.userId,
    walletAddress: input.destinationAddress,
    fiatAmount: undefined,
    direction: 'WITHDRAW',
    correlationId: input.correlationId,
  });
  score += railRisk.score;
  reasons.push(...railRisk.reasons);

  const severity = score >= 90 ? 'CRITICAL' : score >= 70 ? 'HIGH' : score >= 40 ? 'MEDIUM' : 'LOW';
  return {
    allowed: score < Number(process.env.WITHDRAWAL_BLOCK_SCORE || 90),
    score,
    reasons,
    severity,
  };
}

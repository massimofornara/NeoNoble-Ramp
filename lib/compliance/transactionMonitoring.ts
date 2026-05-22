import { query, writeQuery } from '@/lib/exchange/db';
import { screenValue } from '@/lib/aml/sanctionsScreening';
import { getWalletCluster } from '@/lib/aml/walletClustering';
import type { ComplianceDecision } from '@/types/tier1';

function severity(score: number): ComplianceDecision['severity'] {
  if (score >= 90) return 'CRITICAL';
  if (score >= 70) return 'HIGH';
  if (score >= 40) return 'MEDIUM';
  return 'LOW';
}

export async function monitorTransaction(input: {
  userId: string;
  asset: string;
  amount: string;
  type: 'DEPOSIT' | 'WITHDRAWAL' | 'TRADE';
  address?: string;
  correlationId: string;
}) {
  const reasons: string[] = [];
  let score = 0;

  if (input.address) {
    const sanctions = await screenValue(input.address);
    if (sanctions.matched) {
      score += sanctions.severity === 'CRITICAL' ? 100 : 80;
      reasons.push('sanctions_screening_match');
    }
    const cluster = await getWalletCluster(input.address);
    if (cluster?.risk_score) {
      score += cluster.risk_score;
      reasons.push(`wallet_cluster:${cluster.cluster_id}`);
    }
  }

  const velocity = await query<{ count: string; volume: string }>(
    `select count(*)::text, coalesce(sum((payload->>'amount')::numeric), 0)::text as volume
     from compliance_cases
     where user_id = $1 and created_at > now() - interval '24 hours'`,
    [input.userId],
  );
  if (Number(velocity[0]?.count || 0) > Number(process.env.AML_MAX_CASES_PER_DAY || 5)) {
    score += 30;
    reasons.push('aml_case_velocity');
  }

  const decision = { allowed: score < 90, score, reasons, severity: severity(score) };
  if (!decision.allowed || score >= 40) {
    await writeQuery(
      `insert into compliance_cases(user_id, case_type, severity, score, payload)
       values ($1, $2, $3, $4, $5)`,
      [input.userId, input.type, decision.severity, score, JSON.stringify({ input, reasons })],
    );
  }
  return decision;
}

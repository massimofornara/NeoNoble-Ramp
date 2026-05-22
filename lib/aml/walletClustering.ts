import { query, writeQuery } from '@/lib/exchange/db';

export async function assignWalletCluster(input: {
  address: string;
  chain: string;
  clusterId: string;
  riskScore?: number;
  labels?: string[];
}) {
  await writeQuery(
    `insert into wallet_clusters(cluster_id, address, chain, risk_score, labels)
     values ($1, lower($2), $3, $4, $5)
     on conflict(address) do update set cluster_id = excluded.cluster_id, risk_score = excluded.risk_score, labels = excluded.labels, updated_at = now()`,
    [input.clusterId, input.address, input.chain, input.riskScore || 0, input.labels || []],
  );
}

export async function getWalletCluster(address: string) {
  return (await query<{ cluster_id: string; risk_score: number; labels: string[] }>(
    'select cluster_id, risk_score, labels from wallet_clusters where address = lower($1) limit 1',
    [address],
  ))[0] || null;
}

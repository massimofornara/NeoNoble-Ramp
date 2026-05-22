import { query, writeQuery } from '@/lib/exchange/db';

export async function requiredApprovals(input: { asset: string; chain: string; amount: string }) {
  const policies = await query<{ id: string; threshold: number; approvers: string[] }>(
    `select id::text, threshold, approvers
     from multisig_policies
     where active = true
       and (asset is null or asset = $1)
       and (chain is null or chain = $2)
       and amount_threshold <= $3::numeric
     order by amount_threshold desc
     limit 1`,
    [input.asset, input.chain, input.amount],
  );
  return policies[0] || null;
}

export async function requestApprovals(input: {
  requestType: string;
  requestId: string;
  asset: string;
  chain: string;
  amount: string;
}) {
  const policy = await requiredApprovals(input);
  if (!policy) return { required: 0, requested: 0 };
  for (const approver of policy.approvers) {
    await writeQuery(
      `insert into multisig_approvals(request_type, request_id, approver_id)
       values ($1, $2, $3)
       on conflict(request_type, request_id, approver_id) do nothing`,
      [input.requestType, input.requestId, approver],
    );
  }
  return { required: policy.threshold, requested: policy.approvers.length };
}

export async function approveRequest(input: {
  requestType: string;
  requestId: string;
  approverId: string;
  signature?: string;
}) {
  await writeQuery(
    `update multisig_approvals
     set state = 'APPROVED', signature = $4, updated_at = now()
     where request_type = $1 and request_id = $2 and approver_id = $3`,
    [input.requestType, input.requestId, input.approverId, input.signature || null],
  );
}

export async function approvalStatus(input: { requestType: string; requestId: string; threshold: number }) {
  const row = await query<{ approved: string }>(
    `select count(*)::text as approved
     from multisig_approvals
     where request_type = $1 and request_id = $2 and state = 'APPROVED'`,
    [input.requestType, input.requestId],
  );
  const approved = Number(row[0]?.approved || 0);
  return { approved, threshold: input.threshold, satisfied: approved >= input.threshold };
}

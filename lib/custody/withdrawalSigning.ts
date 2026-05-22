import { privateKeyToAccount } from 'viem/accounts';
import type { Hex } from 'viem';
import { query, writeQuery } from '@/lib/exchange/db';
import { getKmsProvider } from '@/lib/custody/keyManagement';
import { assertAddressWhitelisted } from '@/lib/custody/walletService';
import { placeHold } from '@/lib/exchange/ledger';
import { scoreWithdrawalRisk } from '@/lib/custody/withdrawalRisk';
import { requestApprovals, requiredApprovals } from '@/lib/custody/multisigApproval';
import type { CustodyWithdrawalRequest } from '@/types/tier1';

export async function createWithdrawalRequest(input: CustodyWithdrawalRequest) {
  await assertAddressWhitelisted({ ...input, address: input.destinationAddress });
  const risk = await scoreWithdrawalRisk(input);
  if (!risk.allowed) throw new Error(`Withdrawal blocked: ${risk.reasons.join(',')}`);

  const userAccount = await query<{ id: string }>(
    'select id::text from accounts where owner_id = $1 and asset = $2 and account_type = $3 limit 1',
    [input.userId, input.asset, 'USER'],
  );
  if (!userAccount[0]) throw new Error('User asset account not found');

  const holdId = await placeHold({
    accountId: userAccount[0].id,
    asset: input.asset,
    amount: input.amount,
    reason: 'WITHDRAWAL',
    idempotencyKey: `withdrawal-hold:${input.idempotencyKey}`,
    correlationId: input.correlationId,
    metadata: { destinationAddress: input.destinationAddress },
  });

  const row = await writeQuery<{ id: string; state: string }>(
    `insert into withdrawal_requests
      (user_id, asset, chain, amount, destination_address, state, risk_score, idempotency_key, correlation_id, hold_id, metadata)
     values ($1, $2, $3, $4, $5, 'RISK_REVIEW', $6, $7, $8, $9, $10)
     on conflict(idempotency_key) do update set updated_at = now()
     returning id::text, state::text`,
    [
      input.userId,
      input.asset,
      input.chain,
      input.amount,
      input.destinationAddress,
      risk.score,
      input.idempotencyKey,
      input.correlationId,
      holdId,
      JSON.stringify({ risk }),
    ],
  );

  const policy = await requiredApprovals(input);
  if (policy) {
    await requestApprovals({ requestType: 'WITHDRAWAL', requestId: row[0].id, asset: input.asset, chain: input.chain, amount: input.amount });
    await writeQuery("update withdrawal_requests set state = 'APPROVAL_REQUIRED', updated_at = now() where id = $1", [row[0].id]);
  } else {
    await writeQuery("update withdrawal_requests set state = 'APPROVED', updated_at = now() where id = $1", [row[0].id]);
  }

  return { id: row[0].id, risk, holdId };
}

export async function signWithdrawal(withdrawalId: string) {
  const row = await query<{
    id: string;
    asset: string;
    chain: string;
    amount: string;
    destination_address: string;
    state: string;
  }>('select id::text, asset, chain, amount::text, destination_address, state::text from withdrawal_requests where id = $1', [withdrawalId]);
  if (!row[0]) throw new Error('Withdrawal not found');
  if (row[0].state !== 'APPROVED') throw new Error(`Withdrawal must be APPROVED before signing, got ${row[0].state}`);

  const wallet = await query<{ kms_key_id: string }>(
    `select kms_key_id::text from custody_wallets
     where asset = $1 and chain = $2 and tier = 'HOT' and status = 'ACTIVE'
     limit 1`,
    [row[0].asset, row[0].chain],
  );
  if (!wallet[0]?.kms_key_id) throw new Error('No active hot wallet KMS key available');
  const privateKey = await getKmsProvider().exportPrivateKeyForSigning(wallet[0].kms_key_id);
  const account = privateKeyToAccount(privateKey as Hex);
  const payload = JSON.stringify({
    withdrawalId,
    from: account.address,
    to: row[0].destination_address,
    asset: row[0].asset,
    chain: row[0].chain,
    amount: row[0].amount,
  });
  const signature = await account.signMessage({ message: payload });
  await writeQuery(
    "update withdrawal_requests set state = 'SIGNED', signed_payload = $2, updated_at = now() where id = $1",
    [withdrawalId, JSON.stringify({ payload, signature, signer: account.address })],
  );
  return { withdrawalId, signer: account.address, signature };
}

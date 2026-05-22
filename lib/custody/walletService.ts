import { getAddress } from 'viem';
import { query, writeQuery } from '@/lib/exchange/db';
import { getKmsProvider } from '@/lib/custody/keyManagement';
import type { Chain, WalletTier } from '@/types/tier1';

export async function ensureCustodyWallet(input: {
  asset: string;
  chain: Chain;
  tier: WalletTier;
  maxOnlineBalance?: string;
}) {
  const existing = await query<{ id: string; kms_key_id: string | null }>(
    'select id::text, kms_key_id::text from custody_wallets where asset = $1 and chain = $2 and tier = $3',
    [input.asset, input.chain, input.tier],
  );
  if (existing[0]) return existing[0].id;

  const key = input.tier === 'COLD'
    ? null
    : await getKmsProvider().createKey(`${input.asset}-${input.chain}-${input.tier}`, 'WITHDRAWAL_SIGNING');

  const row = await writeQuery<{ id: string }>(
    `insert into custody_wallets(asset, chain, tier, kms_key_id, max_online_balance, metadata)
     values ($1, $2, $3, $4, $5, $6)
     returning id::text`,
    [
      input.asset,
      input.chain,
      input.tier,
      key?.keyId || null,
      input.maxOnlineBalance || '0',
      JSON.stringify({ coldStorage: input.tier === 'COLD' }),
    ],
  );
  return row[0].id;
}

export async function registerDepositAddress(input: {
  userId: string;
  asset: string;
  chain: Chain;
  address: string;
  derivationPath?: string;
}) {
  const normalized = input.chain === 'bitcoin' ? input.address : getAddress(input.address);
  const walletId = await ensureCustodyWallet({ asset: input.asset, chain: input.chain, tier: 'HOT' });
  const row = await writeQuery<{ id: string }>(
    `insert into custody_addresses(wallet_id, owner_id, address, derivation_path, whitelisted, metadata)
     values ($1, $2, $3, $4, false, '{}')
     on conflict(address, wallet_id) do update set owner_id = excluded.owner_id
     returning id::text`,
    [walletId, input.userId, normalized, input.derivationPath || null],
  );
  return { id: row[0].id, address: normalized, walletId };
}

export async function whitelistWithdrawalAddress(input: {
  userId: string;
  asset: string;
  chain: Chain;
  address: string;
  label?: string;
}) {
  const normalized = input.chain === 'bitcoin' ? input.address : getAddress(input.address);
  const row = await writeQuery<{ id: string; cooldown_until: string }>(
    `insert into address_whitelist(user_id, asset, chain, address, label)
     values ($1, $2, $3, $4, $5)
     on conflict(user_id, asset, chain, address) do update set label = excluded.label
     returning id::text, cooldown_until::text`,
    [input.userId, input.asset, input.chain, normalized, input.label || null],
  );
  return { id: row[0].id, address: normalized, cooldownUntil: row[0].cooldown_until };
}

export async function assertAddressWhitelisted(input: {
  userId: string;
  asset: string;
  chain: Chain;
  address: string;
}) {
  const normalized = input.chain === 'bitcoin' ? input.address : getAddress(input.address);
  const row = await query<{ status: string; cooldown_until: string }>(
    `select status, cooldown_until::text from address_whitelist
     where user_id = $1 and asset = $2 and chain = $3 and address = $4`,
    [input.userId, input.asset, input.chain, normalized],
  );
  if (!row[0] || row[0].status !== 'APPROVED') throw new Error('Withdrawal address is not approved');
  if (new Date(row[0].cooldown_until).getTime() > Date.now()) throw new Error('Withdrawal address whitelist cooldown active');
  return true;
}

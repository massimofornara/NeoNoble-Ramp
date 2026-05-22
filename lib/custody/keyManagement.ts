import crypto from 'crypto';
import { privateKeyToAccount } from 'viem/accounts';
import type { Hex } from 'viem';
import { query, writeQuery } from '@/lib/exchange/db';

export type SignerKey = {
  keyId: string;
  publicKey?: string;
  address?: string;
};

export interface KeyManagementProvider {
  createKey(alias: string, purpose: string): Promise<SignerKey>;
  signMessage(keyId: string, message: string): Promise<string>;
  exportPrivateKeyForSigning(keyId: string): Promise<Hex>;
  rotateKey(alias: string, purpose: string): Promise<SignerKey>;
}

function masterKey() {
  const raw = process.env.LOCAL_KMS_MASTER_KEY;
  if (!raw || Buffer.from(raw, 'hex').length !== 32) {
    throw new Error('LOCAL_KMS_MASTER_KEY must be a 32-byte hex key for local KMS provider');
  }
  return Buffer.from(raw, 'hex');
}

function encryptSecret(secret: string) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', masterKey(), iv);
  const encrypted = Buffer.concat([cipher.update(secret, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, encrypted]).toString('base64');
}

function decryptSecret(payload: string) {
  const bytes = Buffer.from(payload, 'base64');
  const iv = bytes.subarray(0, 12);
  const tag = bytes.subarray(12, 28);
  const encrypted = bytes.subarray(28);
  const decipher = crypto.createDecipheriv('aes-256-gcm', masterKey(), iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(encrypted), decipher.final()]).toString('utf8');
}

export class LocalEnvelopeKmsProvider implements KeyManagementProvider {
  async createKey(alias: string, purpose: string): Promise<SignerKey> {
    const existing = await query<{ id: string; public_key: string }>(
      'select id::text, public_key from kms_keys where key_alias = $1 and purpose = $2 and status = $3 order by key_version desc limit 1',
      [alias, purpose, 'ACTIVE'],
    );
    if (existing[0]) return { keyId: existing[0].id, publicKey: existing[0].public_key };

    const privateKey = `0x${crypto.randomBytes(32).toString('hex')}` as Hex;
    const account = privateKeyToAccount(privateKey);
    const row = await writeQuery<{ id: string }>(
      `insert into kms_keys(key_alias, key_version, purpose, provider, public_key, encrypted_private_material, rotation_due_at)
       values ($1, 1, $2, 'LOCAL_ENVELOPE', $3, $4, now() + interval '90 days')
       returning id::text`,
      [alias, purpose, account.address, encryptSecret(privateKey)],
    );
    return { keyId: row[0].id, publicKey: account.address, address: account.address };
  }

  async signMessage(keyId: string, message: string): Promise<string> {
    const privateKey = await this.exportPrivateKeyForSigning(keyId);
    const account = privateKeyToAccount(privateKey);
    return account.signMessage({ message });
  }

  async exportPrivateKeyForSigning(keyId: string): Promise<Hex> {
    const row = await query<{ encrypted_private_material: string; status: string }>(
      'select encrypted_private_material, status from kms_keys where id = $1',
      [keyId],
    );
    if (!row[0] || row[0].status !== 'ACTIVE') throw new Error('KMS key not active');
    return decryptSecret(row[0].encrypted_private_material) as Hex;
  }

  async rotateKey(alias: string, purpose: string): Promise<SignerKey> {
    const latest = await query<{ key_version: number }>(
      'select key_version from kms_keys where key_alias = $1 and purpose = $2 order by key_version desc limit 1',
      [alias, purpose],
    );
    await writeQuery('update kms_keys set status = $3 where key_alias = $1 and purpose = $2 and status = $4', [
      alias,
      purpose,
      'ROTATED',
      'ACTIVE',
    ]);
    const version = (latest[0]?.key_version || 0) + 1;
    const privateKey = `0x${crypto.randomBytes(32).toString('hex')}` as Hex;
    const account = privateKeyToAccount(privateKey);
    const row = await writeQuery<{ id: string }>(
      `insert into kms_keys(key_alias, key_version, purpose, provider, public_key, encrypted_private_material, rotation_due_at)
       values ($1, $2, $3, 'LOCAL_ENVELOPE', $4, $5, now() + interval '90 days')
       returning id::text`,
      [alias, version, purpose, account.address, encryptSecret(privateKey)],
    );
    return { keyId: row[0].id, publicKey: account.address, address: account.address };
  }
}

export function getKmsProvider(): KeyManagementProvider {
  const provider = process.env.KMS_PROVIDER || 'LOCAL_ENVELOPE';
  if (provider !== 'LOCAL_ENVELOPE') {
    throw new Error(`Unsupported KMS_PROVIDER ${provider}; configure a provider adapter before enabling production signing`);
  }
  return new LocalEnvelopeKmsProvider();
}

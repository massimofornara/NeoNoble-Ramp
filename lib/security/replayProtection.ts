import crypto from 'crypto';
import { getRedis } from '@/lib/transak/redis';

export async function assertNonceUnused(input: {
  subject: string;
  nonce: string;
  ttlSeconds?: number;
}) {
  const redis = getRedis();
  if (!redis) return true;
  const digest = crypto.createHash('sha256').update(`${input.subject}:${input.nonce}`).digest('hex');
  const ok = await redis.set(`nonce:${digest}`, '1', 'EX', input.ttlSeconds || 300, 'NX');
  if (!ok) throw new Error('Replay nonce already used');
  return true;
}

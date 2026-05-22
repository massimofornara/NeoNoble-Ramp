import { getRedis } from '@/lib/transak/redis';

export async function slidingWindowLimit(input: {
  subject: string;
  action: string;
  limit: number;
  windowMs: number;
}) {
  const redis = getRedis();
  if (!redis) return { allowed: true, remaining: input.limit };
  const key = `sw:${input.action}:${input.subject}`;
  const now = Date.now();
  const min = now - input.windowMs;
  await redis.zremrangebyscore(key, 0, min);
  await redis.zadd(key, now, `${now}:${Math.random()}`);
  await redis.pexpire(key, input.windowMs);
  const count = await redis.zcard(key);
  return { allowed: count <= input.limit, remaining: Math.max(0, input.limit - count), resetAt: now + input.windowMs };
}

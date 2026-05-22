import Redis from 'ioredis';

let redis: Redis | null = null;

export function getRedis() {
  if (!process.env.REDIS_URL) return null;
  if (!redis) {
    redis = new Redis(process.env.REDIS_URL, {
      maxRetriesPerRequest: 2,
      enableReadyCheck: true,
      lazyConnect: true,
    });
  }
  return redis;
}

export async function enqueueWebhookRetry(payload: unknown, reason: string) {
  const client = getRedis();
  if (!client) return false;
  await client.lpush(
    'transak:webhook:retry',
    JSON.stringify({
      payload,
      reason,
      createdAt: new Date().toISOString(),
    }),
  );
  return true;
}

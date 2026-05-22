import { getRedis } from '@/lib/transak/redis';
import type { StreamTopic } from '@/types/tier1';

const memorySubscribers = new Map<string, Set<(message: unknown) => void>>();

export async function publishStream(topic: StreamTopic, message: Record<string, unknown>) {
  const payload = JSON.stringify({ ...message, topic, timestamp: new Date().toISOString() });
  const redis = getRedis();
  if (redis) {
    await redis.publish(topic, payload);
    await redis.xadd(`stream:${topic}`, 'MAXLEN', '~', 10000, '*', 'payload', payload);
    return;
  }
  for (const subscriber of memorySubscribers.get(topic) || []) subscriber(JSON.parse(payload));
}

export async function subscribeStream(topic: StreamTopic, handler: (message: unknown) => void) {
  const redis = getRedis();
  if (!redis) {
    const set = memorySubscribers.get(topic) || new Set();
    set.add(handler);
    memorySubscribers.set(topic, set);
    return () => set.delete(handler);
  }
  const subscriber = redis.duplicate();
  await subscriber.subscribe(topic);
  subscriber.on('message', (_channel, payload) => handler(JSON.parse(payload)));
  return async () => {
    await subscriber.unsubscribe(topic);
    subscriber.disconnect();
  };
}

export async function replayStream(topic: StreamTopic, from = '-', count = 100) {
  const redis = getRedis();
  if (!redis) return [];
  const rows = await redis.xrange(`stream:${topic}`, from, '+', 'COUNT', count);
  return rows.map(([id, values]) => ({ id, payload: JSON.parse(values[1] || '{}') }));
}

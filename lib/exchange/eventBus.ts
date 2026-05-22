import { getRedis } from '@/lib/transak/redis';
import { log } from '@/lib/transak/logger';
import type { ExchangeEvent } from '@/types/exchange';

const STREAM = process.env.EXCHANGE_EVENT_STREAM || 'exchange:events';
const memoryEvents: ExchangeEvent[] = [];

export async function publishEvent(event: ExchangeEvent) {
  const envelope = {
    ...event,
    createdAt: event.createdAt || new Date().toISOString(),
  };
  const redis = getRedis();
  if (!redis) {
    memoryEvents.push(envelope);
    log.warn('exchange_event_memory_fallback', { type: event.type, aggregateId: event.aggregateId });
    return 'memory';
  }

  await redis.xadd(
    STREAM,
    '*',
    'type',
    envelope.type,
    'aggregateId',
    envelope.aggregateId,
    'correlationId',
    envelope.correlationId,
    'payload',
    JSON.stringify(envelope.payload),
    'createdAt',
    envelope.createdAt,
  );
  return STREAM;
}

export async function readEvents(lastId = '0-0', count = 100) {
  const redis = getRedis();
  if (!redis) return memoryEvents.slice(-count);
  const rows = await redis.xrange(STREAM, lastId, '+', 'COUNT', count);
  return rows.map(([id, values]) => {
    const map: Record<string, string> = { id };
    for (let index = 0; index < values.length; index += 2) {
      map[values[index]] = values[index + 1];
    }
    return {
      type: map.type as ExchangeEvent['type'],
      aggregateId: map.aggregateId,
      correlationId: map.correlationId,
      payload: JSON.parse(map.payload || '{}') as Record<string, unknown>,
      createdAt: map.createdAt,
    };
  });
}

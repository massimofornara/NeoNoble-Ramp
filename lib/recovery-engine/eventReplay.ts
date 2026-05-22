import { readEvents } from '@/lib/exchange/eventBus';
import { writeQuery } from '@/lib/exchange/db';

export async function replayExchangeEvents(from = '0-0', count = 1000) {
  const events = await readEvents(from, count);
  for (const event of events) {
    await writeQuery(
      `insert into recovery_checkpoints(checkpoint_type, stream_id, payload)
       values ('EVENT_REPLAY', $1, $2)`,
      [event.createdAt || event.aggregateId, JSON.stringify(event)],
    );
  }
  return { replayed: events.length };
}

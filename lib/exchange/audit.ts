import crypto from 'crypto';
import type { PoolClient } from 'pg';

function hashPayload(input: unknown) {
  return crypto.createHash('sha256').update(JSON.stringify(input)).digest('hex');
}

export async function appendAuditLog(
  client: PoolClient,
  input: {
    actorId?: string;
    action: string;
    resourceType: string;
    resourceId: string;
    correlationId: string;
    payload?: Record<string, unknown>;
  },
) {
  const previous = await client.query<{ event_hash: string }>(
    'select event_hash from immutable_audit_log order by created_at desc, id desc limit 1',
  );
  const previousHash = previous.rows[0]?.event_hash || null;
  const eventHash = hashPayload({
    previousHash,
    ...input,
  });

  await client.query(
    `insert into immutable_audit_log
      (actor_id, action, resource_type, resource_id, correlation_id, payload, previous_hash, event_hash)
     values ($1, $2, $3, $4, $5, $6, $7, $8)`,
    [
      input.actorId || null,
      input.action,
      input.resourceType,
      input.resourceId,
      input.correlationId,
      JSON.stringify(input.payload || {}),
      previousHash,
      eventHash,
    ],
  );
}

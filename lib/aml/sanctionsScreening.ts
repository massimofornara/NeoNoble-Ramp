import { query, writeQuery } from '@/lib/exchange/db';

export async function upsertSanctionsEntity(input: {
  entityType: 'WALLET' | 'USER' | 'DOMAIN' | 'BANK_ACCOUNT';
  value: string;
  source: string;
  severity?: 'HIGH' | 'CRITICAL';
}) {
  await writeQuery(
    `insert into sanctions_entities(entity_type, value, source, severity)
     values ($1, lower($2), $3, $4)
     on conflict(value) do update set active = true, source = excluded.source, severity = excluded.severity`,
    [input.entityType, input.value, input.source, input.severity || 'HIGH'],
  );
}

export async function screenValue(value: string) {
  const rows = await query<{ entity_type: string; source: string; severity: string }>(
    'select entity_type, source, severity from sanctions_entities where active = true and value = lower($1) limit 1',
    [value],
  );
  return {
    matched: Boolean(rows[0]),
    entityType: rows[0]?.entity_type,
    source: rows[0]?.source,
    severity: rows[0]?.severity || 'LOW',
  };
}

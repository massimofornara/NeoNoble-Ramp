import { getKmsProvider } from '@/lib/custody/keyManagement';
import { query } from '@/lib/exchange/db';

export async function rotateDueSecrets() {
  const due = await query<{ key_alias: string; purpose: string }>(
    `select key_alias, purpose::text
     from kms_keys
     where status = 'ACTIVE' and rotation_due_at is not null and rotation_due_at <= now()`,
  );
  const rotated = [];
  for (const key of due) {
    rotated.push(await getKmsProvider().rotateKey(key.key_alias, key.purpose));
  }
  return { rotated: rotated.length };
}

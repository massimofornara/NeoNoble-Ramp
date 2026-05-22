import { NextResponse } from 'next/server';
import { getRedis } from '@/lib/transak/redis';
import { getPgPool } from '@/lib/transak/db';

export async function GET() {
  const checks: Record<string, string> = { app: 'ok' };
  const pg = getPgPool();
  if (pg) {
    await pg.query('select 1');
    checks.postgres = 'ok';
  } else {
    checks.postgres = 'not_configured';
  }

  const redis = getRedis();
  if (redis) {
    await redis.ping();
    checks.redis = 'ok';
  } else {
    checks.redis = 'not_configured';
  }

  return NextResponse.json({
    status: 'ok',
    checks,
    timestamp: new Date().toISOString(),
  });
}

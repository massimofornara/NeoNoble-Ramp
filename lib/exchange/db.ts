import type { PoolClient } from 'pg';
import { Pool } from 'pg';
import { getPgPool } from '@/lib/transak/db';

let readPool: Pool | null = null;

function getReadPgPool() {
  if (!process.env.DATABASE_REPLICA_URL) return getPgPool();
  if (!readPool) {
    readPool = new Pool({
      connectionString: process.env.DATABASE_REPLICA_URL,
      max: Number(process.env.POSTGRES_READ_POOL_SIZE || 20),
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 5_000,
    });
  }
  return readPool;
}

export async function withPgTransaction<T>(fn: (client: PoolClient) => Promise<T>, isolation = 'SERIALIZABLE') {
  const pool = getPgPool();
  if (!pool) throw new Error('DATABASE_URL is required for exchange core');
  const client = await pool.connect();
  try {
    await client.query('begin');
    await client.query(`set transaction isolation level ${isolation}`);
    const result = await fn(client);
    await client.query('commit');
    return result;
  } catch (error) {
    await client.query('rollback');
    throw error;
  } finally {
    client.release();
  }
}

export async function query<T = Record<string, unknown>>(text: string, params: unknown[] = []) {
  const pool = getReadPgPool();
  if (!pool) throw new Error('DATABASE_URL is required for exchange core');
  const result = await pool.query(text, params);
  return result.rows as T[];
}

export async function writeQuery<T = Record<string, unknown>>(text: string, params: unknown[] = []) {
  const pool = getPgPool();
  if (!pool) throw new Error('DATABASE_URL is required for exchange core');
  const result = await pool.query(text, params);
  return result.rows as T[];
}

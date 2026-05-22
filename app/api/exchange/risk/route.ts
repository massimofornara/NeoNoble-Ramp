import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/exchange/db';

export async function GET(request: NextRequest) {
  const userId = request.nextUrl.searchParams.get('userId') || request.headers.get('x-user-id');
  const rows = await query(
    `select id::text, user_id, wallet_address, risk_type, severity, score, blocked, payload, created_at
     from risk_events
     where ($1::text is null or user_id = $1)
     order by created_at desc
     limit 100`,
    [userId || null],
  );
  return NextResponse.json({ data: rows });
}

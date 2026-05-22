import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/exchange/db';

export async function GET(request: NextRequest) {
  const userId = request.nextUrl.searchParams.get('userId') || request.headers.get('x-user-id');
  if (!userId) return NextResponse.json({ error: 'userId is required' }, { status: 400 });

  const rows = await query(
    `select lt.id::text, lt.transaction_type, lt.state::text, lt.external_provider, lt.external_id,
            lt.metadata, lt.created_at,
            coalesce(json_agg(json_build_object(
              'asset', je.asset,
              'direction', je.direction,
              'amount', je.amount::text,
              'memo', je.memo
            ) order by je.entry_index) filter (where je.id is not null), '[]') as entries
     from ledger_transactions lt
     join journal_entries je on je.ledger_transaction_id = lt.id
     join accounts a on a.id = je.account_id
     where a.owner_id = $1
     group by lt.id
     order by lt.created_at desc
     limit 100`,
    [userId],
  );

  return NextResponse.json({ data: rows });
}

import { NextRequest, NextResponse } from 'next/server';
import { crashRecoveryBootstrap } from '@/lib/recovery-engine/bootstrap';

export async function POST(request: NextRequest) {
  const token = request.headers.get('authorization')?.replace(/^Bearer\s+/i, '');
  if (process.env.RECONCILIATION_ADMIN_TOKEN && token !== process.env.RECONCILIATION_ADMIN_TOKEN) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }
  return NextResponse.json(await crashRecoveryBootstrap());
}

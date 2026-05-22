import { NextRequest, NextResponse } from 'next/server';
import { reconcileTransakCompletedOrders, markStaleTransactionsFailed } from '@/lib/exchange/reconciliation';

export async function POST(request: NextRequest) {
  const token = request.headers.get('authorization')?.replace(/^Bearer\s+/i, '');
  if (process.env.RECONCILIATION_ADMIN_TOKEN && token !== process.env.RECONCILIATION_ADMIN_TOKEN) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const transak = await reconcileTransakCompletedOrders();
  const stale = await markStaleTransactionsFailed();
  return NextResponse.json({ transak, stale });
}

import { NextRequest, NextResponse } from 'next/server';
import { createWithdrawalRequest, signWithdrawal } from '@/lib/custody/withdrawalSigning';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const result = await createWithdrawalRequest({
      userId: String(body.userId || request.headers.get('x-user-id') || ''),
      asset: String(body.asset || 'NENO'),
      chain: body.chain || 'bsc',
      destinationAddress: String(body.destinationAddress),
      amount: String(body.amount),
      idempotencyKey: String(body.idempotencyKey || crypto.randomUUID()),
      correlationId: String(body.correlationId || request.headers.get('x-correlation-id') || crypto.randomUUID()),
    });
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : 'Withdrawal failed' }, { status: 400 });
  }
}

export async function PATCH(request: NextRequest) {
  try {
    const body = await request.json();
    return NextResponse.json(await signWithdrawal(String(body.withdrawalId)));
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : 'Signing failed' }, { status: 400 });
  }
}

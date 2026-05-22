import { NextRequest, NextResponse } from 'next/server';
import { placeClobOrder, cancelClobOrder } from '@/services/execution-engine/executionEngine';
import { query } from '@/lib/exchange/db';

export async function GET(request: NextRequest) {
  const userId = request.nextUrl.searchParams.get('userId') || request.headers.get('x-user-id');
  if (!userId) return NextResponse.json({ error: 'userId is required' }, { status: 400 });
  const rows = await query(
    `select id::text, market, side::text, order_type::text, order_state::text, quantity::text, remaining_quantity::text, price::text, created_at
     from clob_orders
     where user_id = $1
     order by created_at desc
     limit 100`,
    [userId],
  );
  return NextResponse.json({ data: rows });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const result = await placeClobOrder({
      userId: String(body.userId || request.headers.get('x-user-id') || ''),
      market: String(body.market || 'NENO-USDC'),
      side: body.side === 'SELL' ? 'SELL' : 'BUY',
      type: body.type === 'MARKET' || body.type === 'STOP' ? body.type : 'LIMIT',
      quantity: String(body.quantity),
      price: body.price ? String(body.price) : undefined,
      stopPrice: body.stopPrice ? String(body.stopPrice) : undefined,
      timeInForce: body.timeInForce || 'GTC',
      idempotencyKey: String(body.idempotencyKey || crypto.randomUUID()),
      correlationId: String(body.correlationId || request.headers.get('x-correlation-id') || crypto.randomUUID()),
    });
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : 'Order failed' }, { status: 400 });
  }
}

export async function DELETE(request: NextRequest) {
  try {
    const orderId = request.nextUrl.searchParams.get('orderId');
    const userId = request.nextUrl.searchParams.get('userId') || request.headers.get('x-user-id');
    if (!orderId || !userId) return NextResponse.json({ error: 'orderId and userId are required' }, { status: 400 });
    return NextResponse.json(await cancelClobOrder(orderId, userId));
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : 'Cancel failed' }, { status: 400 });
  }
}

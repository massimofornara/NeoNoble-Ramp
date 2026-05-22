import { NextRequest, NextResponse } from 'next/server';
import { readEvents } from '@/lib/exchange/eventBus';

export async function GET(request: NextRequest) {
  const from = request.nextUrl.searchParams.get('from') || '0-0';
  const count = Number(request.nextUrl.searchParams.get('count') || 100);
  return NextResponse.json({ data: await readEvents(from, count) });
}

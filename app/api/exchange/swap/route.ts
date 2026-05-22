import { NextRequest, NextResponse } from 'next/server';
import { executeSwap } from '@/lib/exchange/swapEngine';
import { quoteSwap } from '@/lib/exchange/pricingEngine';
import { getRequestIp, hashIp, rateLimit } from '@/lib/transak/security';
import type { OrderType } from '@/types/exchange';

export async function GET(request: NextRequest) {
  const fromAsset = request.nextUrl.searchParams.get('fromAsset') || 'NENO';
  const toAsset = request.nextUrl.searchParams.get('toAsset') || 'USDC';
  const amountIn = request.nextUrl.searchParams.get('amount') || '1';
  const maxSlippageBps = Number(request.nextUrl.searchParams.get('maxSlippageBps') || 100);
  return NextResponse.json(await quoteSwap({ fromAsset, toAsset, amountIn, maxSlippageBps }));
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const userId = String(body.userId || request.headers.get('x-user-id') || '');
    if (!userId) return NextResponse.json({ error: 'userId is required' }, { status: 400 });

    const limited = await rateLimit({
      key: `swap:${hashIp(getRequestIp(request))}:${userId}`,
      limit: Number(process.env.RISK_MAX_HOURLY_SWAPS || 20),
      windowSeconds: 3600,
    });
    if (!limited.allowed) return NextResponse.json({ error: 'Rate limit exceeded' }, { status: 429 });

    const result = await executeSwap({
      userId,
      fromAsset: String(body.fromAsset || 'NENO').toUpperCase(),
      toAsset: String(body.toAsset || 'USDC').toUpperCase(),
      amount: String(body.amount || ''),
      orderType: (body.orderType === 'LIMIT' ? 'LIMIT' : 'MARKET') as OrderType,
      limitPrice: body.limitPrice ? String(body.limitPrice) : undefined,
      maxSlippageBps: Number(body.maxSlippageBps || 100),
      idempotencyKey: String(body.idempotencyKey || crypto.randomUUID()),
      correlationId: String(body.correlationId || request.headers.get('x-correlation-id') || crypto.randomUUID()),
      walletAddress: body.walletAddress ? String(body.walletAddress) : undefined,
    });
    return NextResponse.json(result);
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : 'Swap failed' }, { status: 400 });
  }
}

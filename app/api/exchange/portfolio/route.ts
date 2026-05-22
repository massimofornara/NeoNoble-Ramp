import { NextRequest, NextResponse } from 'next/server';
import { getPortfolio } from '@/lib/exchange/portfolio';
import { getRequestIp, hashIp, rateLimit } from '@/lib/transak/security';

export async function GET(request: NextRequest) {
  const userId = request.nextUrl.searchParams.get('userId') || request.headers.get('x-user-id');
  if (!userId) return NextResponse.json({ error: 'userId is required' }, { status: 400 });

  const limited = await rateLimit({
    key: `portfolio:${hashIp(getRequestIp(request))}:${userId}`,
    limit: 300,
    windowSeconds: 60,
  });
  if (!limited.allowed) return NextResponse.json({ error: 'Rate limit exceeded' }, { status: 429 });

  return NextResponse.json(await getPortfolio(userId));
}

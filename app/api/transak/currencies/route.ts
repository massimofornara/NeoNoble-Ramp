import { NextRequest, NextResponse } from 'next/server';
import { getCryptoCurrencies, getFiatCurrencies } from '@/lib/transak/client';
import { log } from '@/lib/transak/logger';

export async function GET(request: NextRequest) {
  try {
    const type = request.nextUrl.searchParams.get('type') || 'crypto';
    const query = new URLSearchParams(request.nextUrl.searchParams);
    query.delete('type');

    const data = type === 'fiat' ? await getFiatCurrencies(query) : await getCryptoCurrencies(query);
    return NextResponse.json(data);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    log.error('transak_currencies_failed', { error: message });
    return NextResponse.json({ error: message }, { status: 400 });
  }
}

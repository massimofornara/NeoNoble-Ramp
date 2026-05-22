import { NextResponse } from 'next/server';
import { metricsText } from '@/lib/transak/metrics';

export async function GET() {
  return new NextResponse(await metricsText(), {
    headers: {
      'Content-Type': 'text/plain; version=0.0.4; charset=utf-8',
    },
  });
}

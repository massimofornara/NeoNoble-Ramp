import { NextRequest, NextResponse } from 'next/server';
import { replayStream } from '@/lib/streaming/pubsub';
import type { StreamTopic } from '@/types/tier1';

export async function GET(request: NextRequest) {
  const topic = request.nextUrl.searchParams.get('topic') as StreamTopic | null;
  if (!topic) return NextResponse.json({ error: 'topic is required' }, { status: 400 });
  return NextResponse.json({ data: await replayStream(topic, request.nextUrl.searchParams.get('from') || '-') });
}

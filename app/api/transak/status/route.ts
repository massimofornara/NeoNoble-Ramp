import { NextRequest, NextResponse } from 'next/server';
import { getOrderById, getOrders } from '@/lib/transak/client';
import { logOrderStatus } from '@/lib/transak/db';
import { getRequestIp, hashIp, rateLimit } from '@/lib/transak/security';
import { transakStatusHistogram } from '@/lib/transak/metrics';
import { log } from '@/lib/transak/logger';
import type { TransakOrder } from '@/types/transak';

export async function GET(request: NextRequest) {
  const timer = transakStatusHistogram.startTimer();
  try {
    const limited = await rateLimit({
      key: `transak-status:${hashIp(getRequestIp(request))}`,
      limit: Number(process.env.TRANSAK_STATUS_RATE_LIMIT || 120),
      windowSeconds: 60,
    });
    if (!limited.allowed) {
      return NextResponse.json({ error: 'Rate limit exceeded' }, { status: 429 });
    }

    const orderId = request.nextUrl.searchParams.get('orderId');
    const partnerOrderId = request.nextUrl.searchParams.get('partnerOrderId');

    if (!orderId && !partnerOrderId) {
      return NextResponse.json({ error: 'orderId or partnerOrderId is required' }, { status: 400 });
    }

    let order: TransakOrder | undefined;
    if (orderId) {
      const response = await getOrderById(orderId);
      order = response.data || response.order;
    } else if (partnerOrderId) {
      const query = new URLSearchParams({
        limit: '1',
        skip: '0',
        'filter[sortOrder]': 'desc',
        'filter[partnerOrderId]': partnerOrderId,
      });
      const response = await getOrders(query);
      order = response.data?.[0];
    }

    if (order) await logOrderStatus(order);
    return NextResponse.json({ data: order || null });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    log.error('transak_status_failed', { error: message });
    return NextResponse.json({ error: message }, { status: 400 });
  } finally {
    timer();
  }
}

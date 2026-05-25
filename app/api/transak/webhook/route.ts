import { NextRequest, NextResponse } from 'next/server';
import type { TransakWebhookEnvelope } from '@/types/transak';
import { logKycSession, logOrderStatus, logWebhookEvent, markWebhookProcessed } from '@/lib/transak/db';
import { enqueueWebhookRetry } from '@/lib/transak/redis';
import { assertTransakWebhookIp, assertWebhookNotReplayed, verifyOptionalHmac, verifyTransakWebhook } from '@/lib/transak/security';
import { transakActiveSessionsGauge, transakWebhookCounter } from '@/lib/transak/metrics';
import { log } from '@/lib/transak/logger';
import { prisma } from '@/lib/db';

function mapTransakStatus(status?: string) {
  const normalized = String(status || '').toUpperCase();
  if (normalized === 'COMPLETED') return 'settlement_confirmed';
  if (normalized === 'FAILED' || normalized === 'CANCELLED' || normalized === 'EXPIRED') return 'execution_fallback_active';
  return 'settlement_pending';
}

async function syncLedgerFromTransak(webhookData: Record<string, unknown>) {
  const partnerOrderId = typeof webhookData.partnerOrderId === 'string' ? webhookData.partnerOrderId : undefined;
  if (!partnerOrderId) return;

  const providerOrderId =
    typeof webhookData.orderId === 'string'
      ? webhookData.orderId
      : typeof webhookData.id === 'string'
        ? webhookData.id
        : partnerOrderId;
  const status = mapTransakStatus(typeof webhookData.status === 'string' ? webhookData.status : undefined);
  const existing = await prisma.transaction.findUnique({ where: { id: partnerOrderId } });
  if (!existing) return;

  const transaction = await prisma.transaction.update({
    where: { id: partnerOrderId },
    data: {
      status,
      step: status === 'settlement_confirmed' ? 'finalized' : status === 'execution_fallback_active' ? 'provider_failed_retrying' : 'provider_settlement_pending',
      settlementLayer: 'transak',
      settlementId: providerOrderId,
      finalityStatus: status === 'settlement_confirmed' ? 'finalized' : 'settlement_pending',
      chainStatus: status === 'settlement_confirmed' ? 'provider_settlement_confirmed' : 'provider_routing_active',
      lastSuccessfulRail: status === 'settlement_confirmed' ? 'transak' : undefined,
      rawTxData: webhookData,
      errorMessage: status === 'execution_fallback_active' ? JSON.stringify(webhookData) : null,
    },
  });

  await prisma.transactionEvent.create({
    data: {
      transactionId: transaction.id,
      eventType:
        status === 'settlement_confirmed'
          ? 'provider.transak.settlement_confirmed'
          : status === 'execution_fallback_active'
            ? 'provider.transak.failed'
            : 'provider.transak.updated',
      payload: webhookData,
    },
  });
}

export async function POST(request: NextRequest) {
  let eventId = 'unknown';
  let eventName = 'unknown';
  let rawPayload: TransakWebhookEnvelope | null = null;

  try {
    assertTransakWebhookIp(request);
    const rawBody = await request.text();
    verifyOptionalHmac(rawBody, request);
    rawPayload = JSON.parse(rawBody) as TransakWebhookEnvelope;
    const decoded = verifyTransakWebhook(rawPayload);
    eventId = decoded.eventID || rawPayload.eventID || `${eventName}-${crypto.randomUUID()}`;
    eventName = decoded.eventName || decoded.eventID || rawPayload.eventName || rawPayload.eventID || 'unknown';

    await assertWebhookNotReplayed(eventId);
    await logWebhookEvent({
      eventId,
      eventName,
      rawPayload,
      decodedPayload: decoded,
      replay: false,
    });

    if (decoded.webhookData) {
      await logOrderStatus(decoded.webhookData);
      await syncLedgerFromTransak(decoded.webhookData as Record<string, unknown>);
      if (decoded.webhookData.status === 'COMPLETED' || decoded.webhookData.status === 'FAILED' || decoded.webhookData.status === 'CANCELLED') {
        transakActiveSessionsGauge.dec();
      }
    }

    if (typeof decoded.kycStatus === 'string') {
      await logKycSession({
        eventId,
        partnerUserId: typeof decoded.partnerUserId === 'string' ? decoded.partnerUserId : undefined,
        partnerCustomerId: typeof decoded.partnerCustomerId === 'string' ? decoded.partnerCustomerId : undefined,
        kycStatus: decoded.kycStatus,
        rawPayload,
      });
    }

    await markWebhookProcessed(eventId);
    transakWebhookCounter.inc({ event_name: eventName, result: 'processed' });
    log.info('transak_webhook_processed', { eventId, eventName });

    return NextResponse.json({ ok: true, eventId, eventName });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    transakWebhookCounter.inc({ event_name: eventName, result: 'failed' });
    log.error('transak_webhook_failed', { eventId, eventName, error: message });

    if (rawPayload) {
      await enqueueWebhookRetry(rawPayload, message);
      if (eventId !== 'unknown') await markWebhookProcessed(eventId, message);
    }

    return NextResponse.json({ ok: false, error: message }, { status: message.includes('Replay detected') ? 409 : 400 });
  }
}

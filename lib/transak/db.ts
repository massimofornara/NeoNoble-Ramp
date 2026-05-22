import { Pool } from 'pg';
import type { TransakOrder, TransakWidgetRequest, TransakWebhookData } from '@/types/transak';
import { log } from '@/lib/transak/logger';

let pool: Pool | null = null;

export function getPgPool() {
  if (!process.env.DATABASE_URL) return null;
  if (!pool) {
    pool = new Pool({
      connectionString: process.env.DATABASE_URL,
      max: Number(process.env.POSTGRES_POOL_SIZE || 10),
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 5_000,
    });
  }
  return pool;
}

export async function logSessionCreated(input: {
  partnerOrderId: string;
  partnerCustomerId?: string;
  widgetUrl: string;
  request: TransakWidgetRequest;
  ipHash?: string;
}) {
  const pg = getPgPool();
  if (!pg) return;

  await pg.query(
    `insert into transactions
      (provider, partner_order_id, partner_customer_id, product, status, fiat_currency, crypto_currency, network, wallet_address, widget_url, request_payload, ip_hash)
     values
      ('transak', $1, $2, $3, 'SESSION_CREATED', $4, $5, $6, $7, $8, $9, $10)
     on conflict (partner_order_id) do update
       set widget_url = excluded.widget_url,
           request_payload = excluded.request_payload,
           updated_at = now()`,
    [
      input.partnerOrderId,
      input.partnerCustomerId || null,
      input.request.productsAvailed,
      input.request.fiatCurrency || null,
      input.request.cryptoCurrency || null,
      input.request.network || null,
      input.request.walletAddress || null,
      input.widgetUrl,
      JSON.stringify(input.request),
      input.ipHash || null,
    ],
  );
}

export async function logOrderStatus(order: TransakOrder) {
  const pg = getPgPool();
  if (!pg) return;

  await pg.query(
    `insert into transactions
      (provider, transak_order_id, partner_order_id, partner_customer_id, product, status, fiat_currency, crypto_currency, network, wallet_address, fiat_amount, crypto_amount, fee_fiat, response_payload)
     values
      ('transak', $1, $2, $3, coalesce($4, 'BUY,SELL'), coalesce($5, 'UNKNOWN'), $6, $7, $8, $9, $10, $11, $12, $13)
     on conflict (partner_order_id) do update
       set transak_order_id = coalesce(excluded.transak_order_id, transactions.transak_order_id),
           status = excluded.status,
           response_payload = excluded.response_payload,
           updated_at = now()`,
    [
      order.id || order.orderId || null,
      order.partnerOrderId || order.id || order.orderId || crypto.randomUUID(),
      order.partnerCustomerId || null,
      typeof order.product === 'string' ? order.product : null,
      order.status || null,
      order.fiatCurrency || null,
      order.cryptoCurrency || null,
      order.network || null,
      order.walletAddress || null,
      order.fiatAmount || null,
      order.cryptoAmount || null,
      order.totalFeeInFiat || null,
      JSON.stringify(order),
    ],
  );
}

export async function logWebhookEvent(input: {
  eventId: string;
  eventName: string;
  rawPayload: unknown;
  decodedPayload?: TransakWebhookData;
  replay: boolean;
}) {
  const pg = getPgPool();
  if (!pg) return;

  try {
    await pg.query(
      `insert into webhook_events
        (provider, event_id, event_name, raw_payload, decoded_payload, replay_detected, processed)
       values
        ('transak', $1, $2, $3, $4, $5, false)
       on conflict (provider, event_id) do update
         set replay_detected = true,
             updated_at = now()`,
      [
        input.eventId,
        input.eventName,
        JSON.stringify(input.rawPayload),
        input.decodedPayload ? JSON.stringify(input.decodedPayload) : null,
        input.replay,
      ],
    );
  } catch (error) {
    log.error('webhook_event_log_failed', { error: error instanceof Error ? error.message : String(error) });
    throw error;
  }
}

export async function markWebhookProcessed(eventId: string, errorMessage?: string) {
  const pg = getPgPool();
  if (!pg) return;

  await pg.query(
    `update webhook_events
       set processed = $2,
           error_message = $3,
           processed_at = now(),
           updated_at = now()
     where provider = 'transak' and event_id = $1`,
    [eventId, !errorMessage, errorMessage || null],
  );
}

export async function logKycSession(input: {
  eventId: string;
  partnerUserId?: string;
  partnerCustomerId?: string;
  kycStatus: string;
  rawPayload: unknown;
}) {
  const pg = getPgPool();
  if (!pg) return;

  await pg.query(
    `insert into kyc_sessions
      (provider, partner_user_id, partner_customer_id, kyc_status, event_id, raw_payload)
     values
      ('transak', $1, $2, $3, $4, $5)
     on conflict (provider, event_id) do update
       set kyc_status = excluded.kyc_status,
           raw_payload = excluded.raw_payload,
           updated_at = now()`,
    [
      input.partnerUserId || null,
      input.partnerCustomerId || null,
      input.kycStatus,
      input.eventId,
      JSON.stringify(input.rawPayload),
    ],
  );
}

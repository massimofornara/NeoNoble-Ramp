import { NextRequest, NextResponse } from 'next/server';
import type { TransakProducts, TransakWidgetRequest } from '@/types/transak';
import { createWidgetSession } from '@/lib/transak/client';
import { getPublicTransakConfig } from '@/lib/transak/config';
import { logSessionCreated } from '@/lib/transak/db';
import { hashIp, getRequestIp, assertAllowedOrigin, rateLimit } from '@/lib/transak/security';
import { transakActiveSessionsGauge, transakSessionCounter } from '@/lib/transak/metrics';
import { log } from '@/lib/transak/logger';

const PRODUCTS: TransakProducts[] = ['BUY', 'SELL', 'BUY,SELL'];

function asNumber(value: unknown) {
  if (value === undefined || value === null || value === '') return undefined;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) throw new Error('Amount must be a positive number');
  return parsed;
}

function normalizeBody(body: Record<string, unknown>): TransakWidgetRequest {
  const product = String(body.productsAvailed || 'BUY') as TransakProducts;
  if (!PRODUCTS.includes(product)) throw new Error('productsAvailed must be BUY, SELL, or BUY,SELL');

  const stringList = (value: unknown) => {
    if (Array.isArray(value)) return value.map(String).filter(Boolean);
    if (typeof value === 'string' && value.trim()) return value.split(',').map((item) => item.trim()).filter(Boolean);
    return undefined;
  };

  return {
    productsAvailed: product,
    walletAddress: typeof body.walletAddress === 'string' ? body.walletAddress : undefined,
    email: typeof body.email === 'string' ? body.email : undefined,
    fiatCurrency: typeof body.fiatCurrency === 'string' ? body.fiatCurrency : 'EUR',
    cryptoCurrency: typeof body.cryptoCurrency === 'string' ? body.cryptoCurrency : 'NENO',
    network: typeof body.network === 'string' ? body.network : 'bsc',
    fiatAmount: asNumber(body.fiatAmount),
    cryptoAmount: asNumber(body.cryptoAmount),
    paymentMethod: typeof body.paymentMethod === 'string' ? body.paymentMethod : undefined,
    cryptoCurrencyList: stringList(body.cryptoCurrencyList),
    networks: stringList(body.networks),
    walletRedirection: Boolean(body.walletRedirection),
    disableWalletAddressForm: body.disableWalletAddressForm === undefined ? Boolean(body.walletAddress) : Boolean(body.disableWalletAddressForm),
    partnerOrderId: typeof body.partnerOrderId === 'string' ? body.partnerOrderId : undefined,
    partnerCustomerId: typeof body.partnerCustomerId === 'string' ? body.partnerCustomerId : undefined,
    redirectURL: typeof body.redirectURL === 'string' ? body.redirectURL : undefined,
    exchangeScreenTitle: typeof body.exchangeScreenTitle === 'string' ? body.exchangeScreenTitle : undefined,
    themeColor: typeof body.themeColor === 'string' ? body.themeColor : undefined,
    colorMode: body.colorMode === 'LIGHT' ? 'LIGHT' : 'DARK',
  };
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204 });
}

export async function POST(request: NextRequest) {
  const startedAt = Date.now();
  try {
    assertAllowedOrigin(request);
    const ip = getRequestIp(request);
    const limited = await rateLimit({
      key: `transak-session:${hashIp(ip)}`,
      limit: Number(process.env.TRANSAK_SESSION_RATE_LIMIT || 30),
      windowSeconds: 60,
    });
    if (!limited.allowed) {
      return NextResponse.json({ error: 'Rate limit exceeded' }, { status: 429 });
    }

    const body = normalizeBody(await request.json());
    const origin = request.headers.get('origin') || process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000';
    const session = await createWidgetSession(body, origin);
    const publicConfig = getPublicTransakConfig();

    await logSessionCreated({
      partnerOrderId: session.partnerOrderId,
      partnerCustomerId: session.partnerCustomerId,
      widgetUrl: session.widgetUrl,
      request: body,
      ipHash: hashIp(ip),
    });

    transakSessionCounter.inc({ environment: publicConfig.environment, product: body.productsAvailed });
    transakActiveSessionsGauge.inc();

    log.info('transak_session_created', {
      partnerOrderId: session.partnerOrderId,
      product: body.productsAvailed,
      durationMs: Date.now() - startedAt,
    });

    return NextResponse.json({
      widgetUrl: session.widgetUrl,
      environment: publicConfig.environment,
      partnerOrderId: session.partnerOrderId,
      partnerCustomerId: session.partnerCustomerId,
      pusher: {
        appKey: process.env.NEXT_PUBLIC_TRANSAK_PUSHER_APP_KEY || '1d9ffac87de599c61283',
        cluster: process.env.NEXT_PUBLIC_TRANSAK_PUSHER_CLUSTER || 'ap2',
        channel: `${publicConfig.apiKey}_${session.partnerOrderId}`,
        event: '*',
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    log.error('transak_session_failed', { error: message });
    return NextResponse.json({ error: message }, { status: message.includes('Origin not allowed') ? 403 : 400 });
  }
}

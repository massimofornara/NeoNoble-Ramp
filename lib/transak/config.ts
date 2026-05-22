import type { TransakEnvironment } from '@/types/transak';

const STAGING_WIDGET = 'https://global-stg.transak.com';
const PRODUCTION_WIDGET = 'https://global.transak.com';
const STAGING_API = 'https://api-stg.transak.com';
const PRODUCTION_API = 'https://api.transak.com';
const STAGING_GATEWAY = 'https://api-gateway-stg.transak.com';
const PRODUCTION_GATEWAY = 'https://api-gateway.transak.com';

export function getTransakEnvironment(): TransakEnvironment {
  return process.env.NEXT_PUBLIC_TRANSAK_ENVIRONMENT === 'PRODUCTION' ? 'PRODUCTION' : 'STAGING';
}

export function getTransakUrls(environment: TransakEnvironment = getTransakEnvironment()) {
  const isProduction = environment === 'PRODUCTION';
  return {
    widgetUrl: process.env.TRANSAK_WIDGET_URL || (isProduction ? PRODUCTION_WIDGET : STAGING_WIDGET),
    apiBaseUrl: process.env.TRANSAK_API_BASE_URL || (isProduction ? PRODUCTION_API : STAGING_API),
    apiGatewayUrl: process.env.TRANSAK_API_GATEWAY_URL || (isProduction ? PRODUCTION_GATEWAY : STAGING_GATEWAY),
  };
}

export function getPublicTransakConfig() {
  return {
    apiKey: process.env.NEXT_PUBLIC_TRANSAK_API_KEY || process.env.TRANSAK_API_KEY || '',
    environment: getTransakEnvironment(),
    nenoTokenAddress: process.env.NEXT_PUBLIC_NENO_TOKEN_ADDRESS || '',
    chainId: process.env.NEXT_PUBLIC_CHAIN_ID || '56',
    pusherAppKey: process.env.NEXT_PUBLIC_TRANSAK_PUSHER_APP_KEY || '',
    pusherCluster: process.env.NEXT_PUBLIC_TRANSAK_PUSHER_CLUSTER || '',
  };
}

export function requireServerTransakConfig() {
  const publicConfig = getPublicTransakConfig();
  if (!publicConfig.apiKey) {
    throw new Error('NEXT_PUBLIC_TRANSAK_API_KEY or TRANSAK_API_KEY is required');
  }

  return {
    ...publicConfig,
    accessToken: process.env.TRANSAK_ACCESS_TOKEN || '',
    apiSecret: process.env.TRANSAK_API_SECRET || '',
    webhookSecret: process.env.TRANSAK_WEBHOOK_SECRET || '',
    revenueAccountId: process.env.TRANSAK_REVENUE_ACCOUNT_ID || '',
    allowedOrigins: (process.env.CORS_ORIGINS || 'http://localhost:3000')
      .split(',')
      .map((origin) => origin.trim())
      .filter(Boolean),
  };
}

import type { TransakOrder, TransakWidgetRequest } from '@/types/transak';
import { getTransakEnvironment, getTransakUrls, requireServerTransakConfig } from '@/lib/transak/config';

type AccessTokenCache = {
  token: string;
  expiresAt: number;
};

let accessTokenCache: AccessTokenCache | null = null;

async function transakFetch<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
    cache: 'no-store',
  });

  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(`Transak API ${response.status}: ${JSON.stringify(body)}`);
  }
  return body as T;
}

export async function getTransakAccessToken() {
  const config = requireServerTransakConfig();
  if (config.accessToken) return config.accessToken;

  if (accessTokenCache && accessTokenCache.expiresAt > Date.now() + 60_000) {
    return accessTokenCache.token;
  }

  if (!config.apiSecret) {
    throw new Error('TRANSAK_ACCESS_TOKEN or TRANSAK_API_SECRET is required for Transak session API');
  }

  const { apiBaseUrl } = getTransakUrls();
  const response = await transakFetch<{ data?: { accessToken?: string; expiresAt?: number }; accessToken?: string }>(
    `${apiBaseUrl}/partners/api/v2/refresh-token`,
    {
      method: 'POST',
      headers: {
        'api-secret': config.apiSecret,
      },
      body: JSON.stringify({
        apiKey: config.apiKey,
      }),
    },
  );

  const token = response.data?.accessToken || response.accessToken;
  if (!token) throw new Error('Transak refresh-token response did not include an access token');

  accessTokenCache = {
    token,
    expiresAt: response.data?.expiresAt
      ? (Number(response.data.expiresAt) < 10_000_000_000 ? Number(response.data.expiresAt) * 1000 : Number(response.data.expiresAt))
      : Date.now() + 50 * 60_000,
  };
  return token;
}

export function toOfficialWidgetParams(input: TransakWidgetRequest, origin: string) {
  const config = requireServerTransakConfig();
  const defaultNetwork = input.network || (config.chainId === '56' ? 'bsc' : undefined);
  const partnerOrderId = input.partnerOrderId || `neno-${crypto.randomUUID()}`;
  const hasMultiCryptoList = Boolean(input.cryptoCurrencyList && input.cryptoCurrencyList.length > 1);

  return {
    apiKey: config.apiKey,
    productsAvailed: input.productsAvailed,
    defaultFiatCurrency: input.fiatCurrency || 'EUR',
    defaultCryptoCurrency: input.cryptoCurrency || 'NENO',
    cryptoCurrencyCode: hasMultiCryptoList ? undefined : input.cryptoCurrency || 'NENO',
    defaultNetwork,
    network: defaultNetwork,
    networks: input.networks?.join(',') || defaultNetwork,
    cryptoCurrencyList: input.cryptoCurrencyList?.join(',') || input.cryptoCurrency || 'NENO',
    walletAddress: input.walletAddress,
    disableWalletAddressForm: input.disableWalletAddressForm || undefined,
    walletRedirection: input.walletRedirection || undefined,
    fiatAmount: input.fiatAmount,
    cryptoAmount: input.cryptoAmount,
    paymentMethod: input.paymentMethod,
    redirectURL: input.redirectURL || `${origin}/ramp?transak=complete`,
    partnerOrderId,
    partnerCustomerId: input.partnerCustomerId,
    email: input.email,
    themeColor: input.themeColor || '00f5d4',
    colorMode: input.colorMode || 'DARK',
    exchangeScreenTitle: input.exchangeScreenTitle || 'NeoNoble NENO Ramp',
    referrerDomain: origin,
    hideMenu: true,
  };
}

export async function createWidgetSession(input: TransakWidgetRequest, origin: string) {
  const environment = getTransakEnvironment();
  const { apiGatewayUrl } = getTransakUrls(environment);
  const accessToken = await getTransakAccessToken();
  const queryParams = toOfficialWidgetParams(input, origin);

  const response = await transakFetch<{ data?: { widgetUrl?: string }; widgetUrl?: string }>(
    `${apiGatewayUrl}/api/v2/auth/session`,
    {
      method: 'POST',
      headers: {
        'access-token': accessToken,
      },
      body: JSON.stringify({
        widgetParams: queryParams,
      }),
    },
  );

  const widgetUrl = response.data?.widgetUrl || response.widgetUrl;
  if (!widgetUrl) throw new Error('Transak session response did not include widgetUrl');

  return {
    widgetUrl,
    partnerOrderId: String(queryParams.partnerOrderId),
    partnerCustomerId: input.partnerCustomerId,
    queryParams,
  };
}

export async function getOrderById(orderId: string) {
  const { apiBaseUrl } = getTransakUrls();
  const accessToken = await getTransakAccessToken();
  return transakFetch<{ data?: TransakOrder; order?: TransakOrder }>(`${apiBaseUrl}/partners/api/v2/order/${encodeURIComponent(orderId)}`, {
    method: 'GET',
    headers: {
      'access-token': accessToken,
    },
  });
}

export async function getOrders(searchParams: URLSearchParams) {
  const { apiBaseUrl } = getTransakUrls();
  const accessToken = await getTransakAccessToken();
  return transakFetch<{ data?: TransakOrder[] }>(`${apiBaseUrl}/partners/api/v2/orders?${searchParams.toString()}`, {
    method: 'GET',
    headers: {
      'access-token': accessToken,
    },
  });
}

export async function getCryptoCurrencies(query = new URLSearchParams()) {
  const { apiBaseUrl } = getTransakUrls();
  const config = requireServerTransakConfig();
  query.set('apiKey', config.apiKey);
  return transakFetch(`${apiBaseUrl}/api/v2/currencies/crypto-currencies?${query.toString()}`, { method: 'GET' });
}

export async function getFiatCurrencies(query = new URLSearchParams()) {
  const { apiBaseUrl } = getTransakUrls();
  const config = requireServerTransakConfig();
  query.set('apiKey', config.apiKey);
  return transakFetch(`${apiBaseUrl}/api/v2/currencies/fiat-currencies?${query.toString()}`, { method: 'GET' });
}

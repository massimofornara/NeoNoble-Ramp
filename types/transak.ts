export type TransakEnvironment = 'STAGING' | 'PRODUCTION';
export type TransakProducts = 'BUY' | 'SELL' | 'BUY,SELL';

export type TransakWidgetRequest = {
  productsAvailed: TransakProducts;
  walletAddress?: string;
  email?: string;
  fiatCurrency?: string;
  cryptoCurrency?: string;
  network?: string;
  fiatAmount?: number;
  cryptoAmount?: number;
  paymentMethod?: string;
  cryptoCurrencyList?: string[];
  networks?: string[];
  walletRedirection?: boolean;
  disableWalletAddressForm?: boolean;
  partnerOrderId?: string;
  partnerCustomerId?: string;
  redirectURL?: string;
  exchangeScreenTitle?: string;
  themeColor?: string;
  colorMode?: 'LIGHT' | 'DARK';
};

export type TransakSessionResponse = {
  widgetUrl: string;
  environment: TransakEnvironment;
  partnerOrderId: string;
  partnerCustomerId?: string;
  pusher: {
    appKey: string;
    cluster: string;
    channel: string;
    event: string;
  };
};

export type TransakOrderStatus =
  | 'AWAITING_PAYMENT_FROM_USER'
  | 'PAYMENT_DONE_MARKED_BY_USER'
  | 'PROCESSING'
  | 'PENDING_DELIVERY_FROM_TRANSAK'
  | 'ON_HOLD_PENDING_DELIVERY_FROM_TRANSAK'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'FAILED'
  | 'EXPIRED'
  | string;

export type TransakOrder = {
  id?: string;
  orderId?: string;
  status?: TransakOrderStatus;
  partnerOrderId?: string;
  partnerCustomerId?: string;
  fiatCurrency?: string;
  cryptoCurrency?: string;
  walletAddress?: string;
  network?: string;
  paymentOptionId?: string;
  fiatAmount?: number;
  cryptoAmount?: number;
  totalFeeInFiat?: number;
  createdAt?: string;
  updatedAt?: string;
  [key: string]: unknown;
};

export type TransakWebhookEnvelope = {
  data?: string | TransakWebhookData;
  eventID?: string;
  eventName?: string;
  createdAt?: string;
  [key: string]: unknown;
};

export type TransakWebhookData = {
  eventID?: string;
  eventName?: string;
  webhookData?: TransakOrder;
  status?: string;
  orderId?: string;
  partnerOrderId?: string;
  [key: string]: unknown;
};

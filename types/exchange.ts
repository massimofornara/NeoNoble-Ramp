export type LedgerDirection = 'DEBIT' | 'CREDIT';
export type NormalBalance = 'DEBIT' | 'CREDIT';
export type AccountType = 'USER' | 'EXCHANGE_RESERVE' | 'FEE_REVENUE' | 'CLEARING' | 'LIQUIDITY_POOL' | 'RISK_RESERVE';
export type TransactionState = 'CREATED' | 'PENDING' | 'PROCESSING' | 'SETTLED' | 'FAILED' | 'REVERSED';
export type OrderType = 'MARKET' | 'LIMIT';
export type OrderSide = 'BUY' | 'SELL';

export type MoneyAmount = string;

export type LedgerEntryInput = {
  accountId: string;
  asset: string;
  direction: LedgerDirection;
  amount: MoneyAmount;
  memo?: string;
  metadata?: Record<string, unknown>;
};

export type LedgerTransactionInput = {
  idempotencyKey: string;
  correlationId: string;
  transactionType: string;
  entries: LedgerEntryInput[];
  externalProvider?: string;
  externalId?: string;
  metadata?: Record<string, unknown>;
};

export type LedgerTransactionResult = {
  id: string;
  idempotencyKey: string;
  state: TransactionState;
  journalEntryCount: number;
};

export type ExchangeEvent = {
  type:
    | 'TransactionCreated'
    | 'FiatDepositConfirmed'
    | 'SwapExecuted'
    | 'LedgerUpdated'
    | 'RiskFlagTriggered'
    | 'SettlementReconciled';
  aggregateId: string;
  correlationId: string;
  payload: Record<string, unknown>;
  createdAt?: string;
};

export type SwapQuote = {
  fromAsset: string;
  toAsset: string;
  amountIn: MoneyAmount;
  amountOut: MoneyAmount;
  price: MoneyAmount;
  spreadBps: number;
  slippageBps: number;
  route: Array<{ poolId: string; fromAsset: string; toAsset: string; depth: MoneyAmount }>;
};

export type SwapRequest = {
  userId: string;
  fromAsset: string;
  toAsset: string;
  amount: MoneyAmount;
  orderType: OrderType;
  side?: OrderSide;
  limitPrice?: MoneyAmount;
  maxSlippageBps?: number;
  idempotencyKey: string;
  correlationId: string;
  walletAddress?: string;
};

export type RiskDecision = {
  allowed: boolean;
  score: number;
  reasons: string[];
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
};

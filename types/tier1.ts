export type Chain = 'ethereum' | 'bsc' | 'polygon' | 'bitcoin';
export type WalletTier = 'HOT' | 'WARM' | 'COLD';
export type CustodyWalletStatus = 'ACTIVE' | 'DISABLED' | 'ROTATING' | 'COMPROMISED';
export type KeyPurpose = 'WITHDRAWAL_SIGNING' | 'DEPOSIT_ADDRESS' | 'AUDIT_LOG' | 'SECRET_ENCRYPTION';
export type ApprovalState = 'REQUESTED' | 'APPROVED' | 'REJECTED' | 'EXPIRED';
export type WithdrawalState = 'CREATED' | 'RISK_REVIEW' | 'APPROVAL_REQUIRED' | 'APPROVED' | 'SIGNED' | 'BROADCAST_READY' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export type ClobOrderType = 'MARKET' | 'LIMIT' | 'STOP';
export type ClobOrderSide = 'BUY' | 'SELL';
export type ClobOrderState = 'CREATED' | 'OPEN' | 'PARTIALLY_FILLED' | 'FILLED' | 'CANCELLED';
export type TimeInForce = 'GTC' | 'IOC' | 'FOK';

export type ClobOrderRequest = {
  userId: string;
  market: string;
  side: ClobOrderSide;
  type: ClobOrderType;
  quantity: string;
  price?: string;
  stopPrice?: string;
  timeInForce?: TimeInForce;
  idempotencyKey: string;
  correlationId: string;
};

export type MatchFill = {
  makerOrderId: string;
  takerOrderId: string;
  market: string;
  price: string;
  quantity: string;
  makerUserId: string;
  takerUserId: string;
  makerFee: string;
  takerFee: string;
  tradeId?: string;
};

export type CustodyWithdrawalRequest = {
  userId: string;
  asset: string;
  chain: Chain;
  destinationAddress: string;
  amount: string;
  idempotencyKey: string;
  correlationId: string;
};

export type ComplianceDecision = {
  allowed: boolean;
  score: number;
  reasons: string[];
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
};

export type OracleSourcePrice = {
  source: string;
  price: string;
  weight: number;
  observedAt: string;
};

export type StreamTopic = `user:${string}` | `market:${string}:book` | `market:${string}:trades` | 'system:risk';

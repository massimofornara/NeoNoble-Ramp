export type EventType =
  | "execution.intent_created"
  | "execution.scheduled"
  | "orders.created"
  | "execution.requested"
  | "execution.started"
  | "execution.completed"
  | "execution.failed"
  | "settlement.initiated"
  | "settlement.replacement_broadcast"
  | "settlement.pending_confirmation"
  | "settlement.confirmed"
  | "settlement.failed"
  | "fireblocks.transaction.created"
  | "fireblocks.transaction.submitted"
  | "fireblocks.transaction.updated"
  | "fireblocks.transaction.completed"
  | "fireblocks.transaction.failed"
  | "payout.initiated"
  | "payout.confirmed"
  | "payout.failed"
  | "ledger.append"
  | "reconciliation.requested"
  | "matching.order.accepted"
  | "matching.order.cancelled"
  | "matching.order.filled"
  | "risk.circuit.opened";

export type TransactionState =
  | "INTENT_CREATED"
  | "SCHEDULED"
  | "CREATED"
  | "EXECUTING"
  | "SWAP_EXECUTED"
  | "OFFRAMP_EXECUTED"
  | "EXECUTION_FAILED"
  | "SETTLEMENT_INITIATED"
  | "SETTLEMENT_PENDING_CONFIRMATION"
  | "SETTLEMENT_CONFIRMED"
  | "SETTLEMENT_FAILED"
  | "RECONCILED";

export interface DomainEvent<TPayload = Record<string, unknown>> {
  eventId: string;
  type: EventType;
  transactionId: string;
  timestamp: string;
  payload: TPayload;
  topic?: string;
  partition?: number;
  offset?: number;
  key?: string;
}

export interface DeadLetterRecord {
  id: string;
  event: DomainEvent;
  consumerName: string;
  error: string;
  failedAt: string;
  attempts: number;
}

export interface CreateOrderInput {
  idempotencyKey: string;
  accountId: string;
  type: "swap" | "offramp";
  fromAsset: string;
  toAsset: string;
  fromAmount: string;
  expectedToAmount: string;
  provider?: string;
  destination?: string;
  metadata?: Record<string, unknown>;
}

export interface ExecutionRequestInput {
  idempotencyKey: string;
  transactionId: string;
  accountId: string;
  type: "swap" | "offramp";
  fromAsset: string;
  toAsset: string;
  fromAmount: string;
  expectedToAmount: string;
  provider?: string;
  metadata?: Record<string, unknown>;
}

export interface LedgerAppendInput {
  idempotencyKey: string;
  transactionId: string;
  accountId: string;
  asset: string;
  amount: string;
  direction: "debit" | "credit";
  reason: string;
  metadata?: Record<string, unknown>;
}

export interface LedgerEntry {
  entryId: string;
  eventId: string;
  transactionId: string;
  accountId: string;
  asset: string;
  delta: string;
  amount: string;
  direction: "debit" | "credit";
  reason: string;
  metadata: Record<string, unknown>;
  timestamp: string;
  previousHash: string;
  currentHash: string;
}

export interface ProviderWebhookInput {
  idempotencyKey: string;
  transactionId: string;
  providerReference: string;
  status: "confirmed" | "failed";
  txHash?: string;
  settlementId?: string;
  metadata?: Record<string, unknown>;
}

export interface SettlementProof {
  proofId: string;
  transactionId: string;
  settlementId: string;
  txHash: string;
  adapter: "bsc" | "ethereum" | "fireblocks" | "polygon" | "base" | "arbitrum" | "solana";
  chainId: number;
  status: "initiated" | "confirmed" | "failed";
  requiredConfirmations: number;
  observedConfirmations: number;
  blockNumber?: number;
  receiptStatus?: "success" | "failed" | "pending";
  providerReference?: string;
  payload: Record<string, unknown>;
  timestamp: string;
  previousHash: string;
  currentHash: string;
}

export interface FireblocksTransactionRecord {
  recordId: string;
  orderId: string;
  fireblocksTxId: string;
  fireblocksStatus: string;
  settlementConfirmed: boolean;
  payoutConfirmed: boolean;
  settlementAsset: string;
  settlementAmount: string;
  destinationWallet: string;
  liquidityProvider?: string;
  quoteProvider?: string;
  txHash?: string;
  confirmations: number;
  payload: Record<string, unknown>;
  timestamp: string;
  previousHash: string;
  currentHash: string;
}

export interface ReconciliationReport {
  transactionId: string;
  status: "settlement_confirmed" | "pending" | "failed";
  integrity: boolean;
  ledgerIntegrity: boolean;
  eventReplayValid: boolean;
  settlementProofValid: boolean;
  state: TransactionState | "PENDING";
  checks: {
    stateMachineValid: boolean;
    ledgerConsistent: boolean;
    settlementConfirmationExists: boolean;
    ledgerReconciled: boolean;
    immutableSettlementProof: boolean;
  };
  events: DomainEvent[];
  ledgerEntries: LedgerEntry[];
  errors: string[];
}

export interface EventBus {
  publish<TPayload extends Record<string, unknown>>(
    type: EventType,
    transactionId: string,
    payload: TPayload,
  ): Promise<DomainEvent<TPayload>>;
  append<TPayload extends Record<string, unknown>>(
    type: EventType,
    transactionId: string,
    payload: TPayload,
  ): Promise<DomainEvent<TPayload>>;
  emit<TPayload extends Record<string, unknown>>(
    type: EventType,
    transactionId: string,
    payload: TPayload,
  ): Promise<DomainEvent<TPayload>>;
  subscribe(type: EventType, consumerName: string, handler: (event: DomainEvent) => Promise<void>): void;
  drain(): Promise<void>;
  replayAll(): Promise<void>;
}

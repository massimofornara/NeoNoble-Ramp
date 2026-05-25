import { randomUUID } from "node:crypto";
import type { IncomingHttpHeaders } from "node:http";
import type { EventBus } from "../core/types.js";
import type { ExchangeStore } from "../core/store.js";
import { metrics, startSpan } from "../core/observability.js";
import type { ReconciliationEngine } from "./reconciliationEngine.js";
import { FireblocksClient } from "./fireblocksClient.js";
import { FireblocksWebhookVerifier } from "./fireblocksWebhookVerifier.js";

export interface FireblocksTransferInput {
  idempotencyKey: string;
  orderId?: string;
  accountId: string;
  assetId: string;
  amount: string;
  destinationWallet: string;
  destinationTag?: string;
  purpose: "offramp" | "treasury-transfer" | "settlement";
  fromAsset?: string;
  toAsset?: string;
  chainId?: number;
  liquidityProvider?: string;
  quoteProvider?: string;
  quoteId?: string;
  metadata?: Record<string, unknown>;
}

export interface FireblocksTransferResponse {
  orderId: string;
  fireblocksTxId: string;
  fireblocksStatus: string;
  settlementAsset: string;
  settlementAmount: string;
  destinationWallet: string;
  statusUrl: string;
  duplicate?: boolean;
}

export class FireblocksService {
  private readonly webhookVerifier: FireblocksWebhookVerifier;

  constructor(
    private readonly bus: EventBus,
    private readonly store: ExchangeStore,
    private readonly reconciliationEngine: ReconciliationEngine,
  ) {
    this.webhookVerifier = new FireblocksWebhookVerifier(store.webhookNonces);
  }

  readiness(): Record<string, unknown> {
    const client = FireblocksClient.readinessFromEnv();
    const assetMissing = ["FIREBLOCKS_NENO_ASSET_ID", "FIREBLOCKS_STABLECOIN_ASSET_ID"].filter((key) => !process.env[key]);
    return {
      ...client,
      configured: client.configured && assetMissing.length === 0,
      missing: [...client.missing, ...assetMissing],
      circuitBreakerOpen: process.env.FIREBLOCKS_PAYOUT_CIRCUIT_BREAKER_OPEN === "1",
      supportedChains: ["ethereum", "arbitrum", "base", "polygon", "bsc", "solana"],
      custodyProvider: "Fireblocks",
    };
  }

  async vaultStatus(): Promise<Record<string, unknown>> {
    const client = FireblocksClient.fromEnv();
    const vault = await client.getVaultAccount();
    const assetIds = [process.env.FIREBLOCKS_NENO_ASSET_ID, process.env.FIREBLOCKS_STABLECOIN_ASSET_ID].filter((value): value is string => Boolean(value));
    const balances: Record<string, unknown> = {};
    for (const assetId of assetIds) {
      try {
        balances[assetId] = await client.getVaultAssetBalance(client.config.vaultAccountId, assetId);
      } catch (error) {
        balances[assetId] = { error: error instanceof Error ? error.message : String(error) };
      }
    }
    return {
      configured: true,
      vaultAccountId: client.config.vaultAccountId,
      vault,
      balances,
    };
  }

  async createVaultTransfer(input: FireblocksTransferInput): Promise<FireblocksTransferResponse> {
    assertCircuitClosed();
    assertPositiveDecimal(input.amount, "amount");
    assertAssetId(input.assetId);
    assertDestination(input.destinationWallet);
    const existing = this.store.idempotency.get<FireblocksTransferResponse>("fireblocks.transfer.create", input.idempotencyKey);
    if (existing) return { ...existing, duplicate: true };

    const client = FireblocksClient.fromEnv();
    const orderId = input.orderId || randomUUID();
    const trace = startSpan("fireblocks.createVaultTransfer", orderId);
    try {
      await this.ensureIntentLifecycle(orderId, input);
      const externalTxId = `fb:${orderId}:${input.idempotencyKey}`.slice(0, 255);
      const created = await client.createTransaction({
        assetId: input.assetId,
        amount: input.amount,
        source: {
          type: "VAULT_ACCOUNT",
          id: client.config.vaultAccountId,
        },
        destination: {
          type: "ONE_TIME_ADDRESS",
          oneTimeAddress: {
            address: input.destinationWallet,
            tag: input.destinationTag,
          },
        },
        note: `NeoNoble ${input.purpose} ${orderId}`,
        externalTxId,
        feeLevel: fireblocksFeeLevel(),
      });
      const fireblocksTxId = stringField(created, "id") ?? stringField(created, "txId") ?? stringField(created, "transactionId");
      if (!fireblocksTxId) throw new Error("Fireblocks create transaction response missing transaction id");
      const fireblocksStatus = normalizeFireblocksStatus(stringField(created, "status") ?? "CREATED");
      const txHash = txHashFrom(created);

      await this.store.fireblocksTransactions.append({
        orderId,
        fireblocksTxId,
        fireblocksStatus,
        settlementConfirmed: false,
        payoutConfirmed: false,
        settlementAsset: input.assetId,
        settlementAmount: input.amount,
        destinationWallet: input.destinationWallet,
        liquidityProvider: input.liquidityProvider,
        quoteProvider: input.quoteProvider,
        txHash,
        confirmations: confirmationsFrom(created),
        payload: redactedPayload({
          ...created,
          purpose: input.purpose,
          externalTxId,
          quoteId: input.quoteId,
          metadata: input.metadata ?? {},
        }),
      });

      await this.bus.publish("fireblocks.transaction.created", orderId, {
        provider: "fireblocks",
        custodyProvider: "Fireblocks",
        fireblocksTxId,
        fireblocksStatus,
        settlementAsset: input.assetId,
        settlementAmount: input.amount,
        destinationWallet: input.destinationWallet,
        liquidityProvider: input.liquidityProvider,
        quoteProvider: input.quoteProvider,
        txHash,
        accountId: input.accountId,
        type: input.purpose,
        chainId: input.chainId,
        metadata: input.metadata ?? {},
      });
      if (input.purpose === "offramp") {
        await this.bus.publish("payout.initiated", orderId, {
          provider: "fireblocks",
          custodyProvider: "Fireblocks",
          fireblocksTxId,
          fireblocksStatus,
          settlementAsset: input.assetId,
          settlementAmount: input.amount,
          destinationWallet: input.destinationWallet,
          rule: "payout_confirmed_only_after_fireblocks_completed_and_chain_finality",
        });
      }
      if (txHash && isBroadcastLikeStatus(fireblocksStatus)) {
        await this.ensureExecutionCompleted(orderId, input, fireblocksTxId, fireblocksStatus, txHash);
      }

      const response = {
        orderId,
        fireblocksTxId,
        fireblocksStatus,
        settlementAsset: input.assetId,
        settlementAmount: input.amount,
        destinationWallet: input.destinationWallet,
        statusUrl: `/offramp/status/${orderId}`,
      };
      trace.end({ fireblocksStatus });
      return this.store.idempotency.set("fireblocks.transfer.create", input.idempotencyKey, response);
    } catch (error) {
      trace.end({ error: error instanceof Error ? error.message : String(error) });
      metrics.inc("fireblocks_transfer_failures_total", { reason: classifyFireblocksFailure(error) });
      throw error;
    }
  }

  async handleWebhook(rawBody: string, headers: IncomingHttpHeaders): Promise<Record<string, unknown>> {
    const verification = await this.webhookVerifier.verify(rawBody, headers);
    const payload = JSON.parse(rawBody) as Record<string, unknown>;
    const txPayload = fireblocksTransactionPayload(payload);
    const fireblocksTxId = stringField(txPayload, "id") ?? stringField(txPayload, "txId") ?? stringField(txPayload, "transactionId");
    if (!fireblocksTxId) throw new Error("Fireblocks webhook missing transaction id");
    const created = this.findCreatedEvent(fireblocksTxId);
    const orderId = created.transactionId;
    const expected = expectedTransferFrom(created.payload);
    const status = normalizeFireblocksStatus(stringField(txPayload, "status") ?? stringField(payload, "status") ?? "");
    const txHash = txHashFrom(txPayload);
    const confirmations = confirmationsFrom(txPayload);

    await this.bus.publish("fireblocks.transaction.updated", orderId, {
      provider: "fireblocks",
      fireblocksTxId,
      fireblocksStatus: status,
      txHash,
      confirmations,
      verificationMethod: verification.method,
      payload: redactedPayload(txPayload),
    });

    if (isFailedStatus(status)) {
      await this.recordFireblocksState(orderId, fireblocksTxId, status, expected, txHash, confirmations, txPayload, false, false);
      await this.bus.publish("fireblocks.transaction.failed", orderId, {
        provider: "fireblocks",
        fireblocksTxId,
        fireblocksStatus: status,
        reason: stringField(txPayload, "subStatus") ?? "FIREBLOCKS_TRANSACTION_FAILED",
      });
      await this.bus.publish("payout.failed", orderId, {
        provider: "fireblocks",
        fireblocksTxId,
        fireblocksStatus: status,
        reason: "Fireblocks transaction reached failed terminal state",
      });
      return { orderId, fireblocksTxId, status, accepted: true, terminal: "failed" };
    }

    if (!isBroadcastLikeStatus(status)) {
      await this.recordFireblocksState(orderId, fireblocksTxId, status, expected, txHash, confirmations, txPayload, false, false);
      return { orderId, fireblocksTxId, status, accepted: true, terminal: false };
    }

    const client = FireblocksClient.fromEnv();
    const remote = await client.getTransactionById(fireblocksTxId);
    const merged = { ...txPayload, ...remote };
    const mergedStatus = normalizeFireblocksStatus(stringField(merged, "status") ?? status);
    const mergedTxHash = txHashFrom(merged);
    if (!mergedTxHash) throw new Error("Fireblocks transaction is broadcast-like but missing txHash");
    await this.ensureExecutionCompleted(orderId, expected, fireblocksTxId, mergedStatus, mergedTxHash);

    const finality = await this.verifyFinality(merged, expected);
    if (!finality.valid) {
      await this.ensureSettlementInitiated(orderId, expected, fireblocksTxId, mergedStatus, mergedTxHash, finality);
      await this.recordFireblocksState(orderId, fireblocksTxId, mergedStatus, expected, mergedTxHash, finality.confirmations, merged, false, false);
      return { orderId, fireblocksTxId, status: mergedStatus, accepted: true, settlement: "pending_confirmation", finality };
    }

    await this.ensureSettlementConfirmed(orderId, expected, fireblocksTxId, mergedStatus, mergedTxHash, finality, merged);
    await this.bus.drain();
    const report = await this.reconciliationEngine.reconcile(orderId);
    await this.bus.drain();
    if (report.status !== "settlement_confirmed" || !report.integrity) {
      throw new Error(`Fireblocks settlement completed but reconciliation failed: ${report.errors.join("; ")}`);
    }
    const payoutAlreadyConfirmed = this.store.events.byTransaction(orderId).some((event) => event.type === "payout.confirmed");
    if (!payoutAlreadyConfirmed) {
      await this.bus.publish("payout.confirmed", orderId, {
        provider: "fireblocks",
        custodyProvider: "Fireblocks",
        fireblocksTxId,
        fireblocksStatus: mergedStatus,
        txHash: mergedTxHash,
        confirmations: finality.confirmations,
        destinationWallet: expected.destinationWallet,
        settlementAsset: expected.assetId,
        settlementAmount: expected.amount,
        reconciliationIntegrity: report.integrity,
      });
    }
    await this.recordFireblocksState(orderId, fireblocksTxId, mergedStatus, expected, mergedTxHash, finality.confirmations, merged, true, true);
    metrics.observe("fireblocks_payout_completion_time_ms", Date.now() - Date.parse(created.timestamp), { asset: expected.assetId });
    return { orderId, fireblocksTxId, status: mergedStatus, accepted: true, settlement: "settlement_confirmed", payout: "payout_confirmed" };
  }

  async status(orderId: string): Promise<Record<string, unknown>> {
    const report = await this.reconciliationEngine.reconcile(orderId);
    await this.bus.drain();
    const events = this.store.events.byTransaction(orderId);
    const latestRecord = this.safeFireblocksRecords(orderId).at(-1);
    const created = events.find((event) => event.type === "fireblocks.transaction.created");
    const confirmed = events.find((event) => event.type === "settlement.confirmed");
    const payoutConfirmed = events.find((event) => event.type === "payout.confirmed");
    return {
      order_id: orderId,
      asset: latestRecord?.settlementAsset ?? created?.payload.settlementAsset,
      amount: latestRecord?.settlementAmount ?? created?.payload.settlementAmount,
      swap_provider: created?.payload.quoteProvider ?? created?.payload.liquidityProvider ?? "0x/1inch/OTC if configured",
      custody_provider: "Fireblocks",
      fireblocks_tx_id: latestRecord?.fireblocksTxId ?? created?.payload.fireblocksTxId,
      fireblocks_status: latestRecord?.fireblocksStatus,
      tx_hash: latestRecord?.txHash ?? confirmed?.payload.txHash,
      settlement_confirmed: report.status === "settlement_confirmed" && report.integrity,
      payout_confirmed: Boolean(payoutConfirmed),
      confirmations: latestRecord?.confirmations ?? confirmed?.payload.observedConfirmations ?? 0,
      destination_wallet: latestRecord?.destinationWallet ?? created?.payload.destinationWallet,
      reconciliation: {
        status: report.status,
        integrity: report.integrity,
        ledgerIntegrity: report.ledgerIntegrity,
        settlementProofValid: report.settlementProofValid,
      },
      fireblocksAuditHashChain: this.store.fireblocksTransactions.verifyHashChain(),
      events: events.map((event) => ({ eventId: event.eventId, type: event.type, timestamp: event.timestamp })),
    };
  }

  private async ensureIntentLifecycle(orderId: string, input: FireblocksTransferInput): Promise<void> {
    const existing = this.store.events.byTransaction(orderId);
    const traceId = orderId.replace(/-/g, "").padEnd(32, "0").slice(0, 32);
    if (!existing.some((event) => event.type === "execution.intent_created")) {
      await this.bus.publish("execution.intent_created", orderId, {
        intentId: orderId,
        traceId,
        userId: input.accountId,
        accountId: input.accountId,
        type: input.purpose === "offramp" ? "offramp" : "swap",
        fromAsset: input.fromAsset ?? input.assetId,
        toAsset: input.toAsset ?? input.assetId,
        fromAmount: input.amount,
        expectedToAmount: input.amount,
        provider: "fireblocks",
        executionMode: "fireblocks-custody",
        metadata: {
          ...(input.metadata ?? {}),
          traceId,
          settlementRail: "fireblocks-managed",
        },
      });
    }
    if (!existing.some((event) => event.type === "execution.scheduled")) {
      await this.bus.publish("execution.scheduled", orderId, {
        traceId,
        provider: "fireblocks",
        route: ["FireblocksVaultTransfer"],
        twap: false,
        executionPlan: {
          style: "custody-transfer",
          custodyProvider: "Fireblocks",
        },
      });
    }
    if (!existing.some((event) => event.type === "execution.started")) {
      await this.bus.publish("execution.started", orderId, {
        traceId,
        accountId: input.accountId,
        type: input.purpose === "offramp" ? "offramp" : "swap",
        provider: "fireblocks",
        fromAsset: input.fromAsset ?? input.assetId,
        toAsset: input.toAsset ?? input.assetId,
        fromAmount: input.amount,
        expectedToAmount: input.amount,
        metadata: {
          settlementRail: "fireblocks-managed",
        },
      });
    }
  }

  private async ensureExecutionCompleted(
    orderId: string,
    expected: ExpectedTransfer,
    fireblocksTxId: string,
    fireblocksStatus: string,
    txHash: string,
  ): Promise<void> {
    if (this.store.events.byTransaction(orderId).some((event) => event.type === "execution.completed")) return;
    await this.bus.publish("execution.completed", orderId, {
      traceId: orderId.replace(/-/g, "").padEnd(32, "0").slice(0, 32),
      accountId: expected.accountId,
      type: expected.purpose === "offramp" ? "offramp" : "swap",
      provider: "fireblocks",
      fromAsset: expected.fromAsset ?? expected.assetId,
      toAsset: expected.toAsset ?? expected.assetId,
      fromAmount: expected.amount,
      executedAmount: expected.amount,
      executionReference: fireblocksTxId,
      txHash,
      metadata: {
        settlementRail: "fireblocks-managed",
        fireblocksTxId,
        fireblocksStatus,
        destinationWallet: expected.destinationWallet,
      },
    });
  }

  private async ensureSettlementInitiated(
    orderId: string,
    expected: ExpectedTransfer,
    fireblocksTxId: string,
    fireblocksStatus: string,
    txHash: string,
    finality: FireblocksFinality,
  ): Promise<void> {
    const events = this.store.events.byTransaction(orderId);
    if (events.some((event) => event.type === "settlement.initiated")) return;
    const settlementId = `fb_set_${fireblocksTxId}`;
    const initiatedProof = await this.store.settlementProofs.append({
      transactionId: orderId,
      settlementId,
      txHash,
      adapter: adapterForChain(expected.chainId),
      chainId: expected.chainId ?? chainIdForAdapter(adapterForChain(expected.chainId)),
      status: "initiated",
      requiredConfirmations: finality.requiredConfirmations,
      observedConfirmations: finality.confirmations,
      blockNumber: finality.blockNumber,
      receiptStatus: finality.receiptStatus,
      providerReference: `fireblocks:${fireblocksTxId}`,
      payload: {
        provider: "fireblocks",
        fireblocksTxId,
        fireblocksStatus,
        destinationWallet: expected.destinationWallet,
        finalitySource: finality.source,
      },
    });
    await this.bus.publish("settlement.initiated", orderId, {
      traceId: orderId.replace(/-/g, "").padEnd(32, "0").slice(0, 32),
      provider: "fireblocks",
      adapter: initiatedProof.adapter,
      chainId: initiatedProof.chainId,
      settlementId,
      txHash,
      accountId: expected.accountId,
      asset: expected.assetId,
      amount: expected.amount,
      executionReference: fireblocksTxId,
      requiredConfirmations: finality.requiredConfirmations,
      observedConfirmations: finality.confirmations,
      blockNumber: finality.blockNumber,
      receiptStatus: finality.receiptStatus,
      settlementProofHash: initiatedProof.currentHash,
      valuation: expected.metadata?.valuation ?? {},
      metadata: {
        fireblocksTxId,
        destinationWallet: expected.destinationWallet,
      },
    });
    await this.bus.publish("settlement.pending_confirmation", orderId, {
      provider: "fireblocks",
      adapter: initiatedProof.adapter,
      chainId: initiatedProof.chainId,
      settlementId,
      txHash,
      requiredConfirmations: finality.requiredConfirmations,
      observedConfirmations: finality.confirmations,
      receiptStatus: finality.receiptStatus,
      metadata: {
        confirmationSource: finality.source,
      },
    });
  }

  private async ensureSettlementConfirmed(
    orderId: string,
    expected: ExpectedTransfer,
    fireblocksTxId: string,
    fireblocksStatus: string,
    txHash: string,
    finality: FireblocksFinality,
    payload: Record<string, unknown>,
  ): Promise<void> {
    await this.ensureSettlementInitiated(orderId, expected, fireblocksTxId, fireblocksStatus, txHash, finality);
    if (this.store.events.byTransaction(orderId).some((event) => event.type === "settlement.confirmed")) return;
    const settlementId = `fb_set_${fireblocksTxId}`;
    const proof = await this.store.settlementProofs.append({
      transactionId: orderId,
      settlementId,
      txHash,
      adapter: adapterForChain(expected.chainId),
      chainId: expected.chainId ?? chainIdForAdapter(adapterForChain(expected.chainId)),
      status: "confirmed",
      requiredConfirmations: finality.requiredConfirmations,
      observedConfirmations: finality.confirmations,
      blockNumber: finality.blockNumber,
      receiptStatus: "success",
      providerReference: `fireblocks:${fireblocksTxId}`,
      payload: {
        provider: "fireblocks",
        fireblocksTxId,
        fireblocksStatus,
        destinationWallet: expected.destinationWallet,
        finalitySource: finality.source,
        fireblocksPayload: redactedPayload(payload),
      },
    });
    await this.bus.publish("fireblocks.transaction.completed", orderId, {
      provider: "fireblocks",
      fireblocksTxId,
      fireblocksStatus,
      txHash,
      confirmations: finality.confirmations,
      destinationWallet: expected.destinationWallet,
    });
    await this.bus.publish("settlement.confirmed", orderId, {
      traceId: orderId.replace(/-/g, "").padEnd(32, "0").slice(0, 32),
      providerReference: `fireblocks:${fireblocksTxId}`,
      settlementId,
      txHash,
      adapter: proof.adapter,
      chainId: proof.chainId,
      requiredConfirmations: finality.requiredConfirmations,
      observedConfirmations: finality.confirmations,
      blockNumber: finality.blockNumber,
      settlementProofHash: proof.currentHash,
      metadata: {
        confirmationSource: finality.source,
        fireblocksTxId,
      },
    });
    metrics.observe("fireblocks_settlement_latency_ms", Date.now() - Date.parse(this.findCreatedEvent(fireblocksTxId).timestamp), {
      asset: expected.assetId,
    });
  }

  private async verifyFinality(payload: Record<string, unknown>, expected: ExpectedTransfer): Promise<FireblocksFinality> {
    const status = normalizeFireblocksStatus(stringField(payload, "status") ?? "");
    const txHash = txHashFrom(payload);
    const requiredConfirmations = Number(process.env.FIREBLOCKS_CONFIRMATION_THRESHOLD ?? process.env.CONFIRMATION_DEPTH ?? 1);
    const confirmations = confirmationsFrom(payload);
    const blockNumber = numberField(payload, "blockNumber") ?? blockNumberFromBlockInfo(payload);
    if (status !== "COMPLETED") {
      return {
        valid: false,
        source: "fireblocks-status",
        confirmations,
        requiredConfirmations,
        receiptStatus: "pending",
        blockNumber,
      };
    }
    validateCompletedPayload(payload, expected, txHash);
    if (confirmations >= requiredConfirmations) {
      return {
        valid: true,
        source: "fireblocks-completed-confirmation-count",
        confirmations,
        requiredConfirmations,
        receiptStatus: "success",
        blockNumber,
      };
    }
    return {
      valid: false,
      source: "fireblocks-completed-confirmation-count",
      confirmations,
      requiredConfirmations,
      receiptStatus: confirmations > 0 ? "success" : "pending",
      blockNumber,
    };
  }

  private findCreatedEvent(fireblocksTxId: string) {
    const event = this.store.events.all().find(
      (candidate) => candidate.type === "fireblocks.transaction.created" && candidate.payload.fireblocksTxId === fireblocksTxId,
    );
    if (!event) throw new Error(`Unknown Fireblocks transaction id: ${fireblocksTxId}`);
    return event;
  }

  private async recordFireblocksState(
    orderId: string,
    fireblocksTxId: string,
    status: string,
    expected: ExpectedTransfer,
    txHash: string | undefined,
    confirmations: number,
    payload: Record<string, unknown>,
    settlementConfirmed: boolean,
    payoutConfirmed: boolean,
  ): Promise<void> {
    await this.store.fireblocksTransactions.append({
      orderId,
      fireblocksTxId,
      fireblocksStatus: status,
      settlementConfirmed,
      payoutConfirmed,
      settlementAsset: expected.assetId,
      settlementAmount: expected.amount,
      destinationWallet: expected.destinationWallet,
      liquidityProvider: expected.liquidityProvider,
      quoteProvider: expected.quoteProvider,
      txHash,
      confirmations,
      payload: redactedPayload(payload),
    });
  }

  private safeFireblocksRecords(orderId: string) {
    try {
      return this.store.fireblocksTransactions.byOrder(orderId);
    } catch {
      return [];
    }
  }
}

interface ExpectedTransfer {
  accountId: string;
  assetId: string;
  amount: string;
  destinationWallet: string;
  purpose: "offramp" | "treasury-transfer" | "settlement";
  fromAsset?: string;
  toAsset?: string;
  chainId?: number;
  liquidityProvider?: string;
  quoteProvider?: string;
  metadata?: Record<string, unknown>;
}

interface FireblocksFinality {
  valid: boolean;
  source: string;
  confirmations: number;
  requiredConfirmations: number;
  receiptStatus: "success" | "failed" | "pending";
  blockNumber?: number;
}

function expectedTransferFrom(payload: Record<string, unknown>): ExpectedTransfer {
  return {
    accountId: String(payload.accountId ?? "unknown-account"),
    assetId: String(payload.settlementAsset ?? ""),
    amount: String(payload.settlementAmount ?? ""),
    destinationWallet: String(payload.destinationWallet ?? ""),
    purpose: payload.type === "offramp" ? "offramp" : "settlement",
    fromAsset: optionalString(payload.fromAsset),
    toAsset: optionalString(payload.toAsset),
    chainId: payload.chainId === undefined ? undefined : Number(payload.chainId),
    liquidityProvider: optionalString(payload.liquidityProvider),
    quoteProvider: optionalString(payload.quoteProvider),
    metadata: asRecord(payload.metadata),
  };
}

function fireblocksTransactionPayload(payload: Record<string, unknown>): Record<string, unknown> {
  for (const candidate of [payload.data, payload.resource, payload.transaction]) {
    const record = asRecord(candidate);
    if (Object.keys(record).length > 0) return record;
  }
  return payload;
}

function normalizeFireblocksStatus(value: string): string {
  return String(value || "UNKNOWN").trim().toUpperCase();
}

function isBroadcastLikeStatus(status: string): boolean {
  return ["BROADCASTING", "CONFIRMING", "COMPLETED"].includes(normalizeFireblocksStatus(status));
}

function isFailedStatus(status: string): boolean {
  return ["FAILED", "REJECTED", "CANCELLED", "CANCELED", "BLOCKED", "TIMEOUT"].includes(normalizeFireblocksStatus(status));
}

function txHashFrom(payload: Record<string, unknown>): string | undefined {
  return (
    stringField(payload, "txHash") ??
    stringField(payload, "transactionHash") ??
    stringField(payload, "hash") ??
    stringField(asRecord(payload.txInfo), "txHash") ??
    stringField(asRecord(payload.networkRecords), "txHash")
  );
}

function confirmationsFrom(payload: Record<string, unknown>): number {
  return (
    numberField(payload, "numOfConfirmations") ??
    numberField(payload, "confirmations") ??
    numberField(payload, "numberOfConfirmations") ??
    numberField(asRecord(payload.txInfo), "confirmations") ??
    numberField(firstRecord(payload.networkRecords), "numOfConfirmations") ??
    0
  );
}

function blockNumberFromBlockInfo(payload: Record<string, unknown>): number | undefined {
  return numberField(asRecord(payload.blockInfo), "blockHeight") ?? numberField(asRecord(payload.blockInfo), "blockNumber");
}

function firstRecord(value: unknown): Record<string, unknown> {
  return Array.isArray(value) ? asRecord(value[0]) : asRecord(value);
}

function validateCompletedPayload(payload: Record<string, unknown>, expected: ExpectedTransfer, txHash: string | undefined): void {
  if (!txHash || !validTxHash(txHash, expected.chainId)) throw new Error("Fireblocks completed transaction is missing a valid tx hash");
  const assetId = stringField(payload, "assetId") ?? stringField(payload, "asset");
  if (assetId && assetId !== expected.assetId) throw new Error(`Fireblocks asset mismatch: expected ${expected.assetId}, got ${assetId}`);
  const amount = stringField(payload, "amount") ?? stringField(payload, "requestedAmount");
  if (amount && decimalToComparable(amount) !== decimalToComparable(expected.amount)) {
    throw new Error(`Fireblocks amount mismatch: expected ${expected.amount}, got ${amount}`);
  }
  const destination = destinationFrom(payload);
  if (destination && destination.toLowerCase() !== expected.destinationWallet.toLowerCase()) {
    throw new Error("Fireblocks destination wallet mismatch");
  }
}

function destinationFrom(payload: Record<string, unknown>): string | undefined {
  return (
    stringField(payload, "destinationAddress") ??
    stringField(asRecord(payload.destination), "address") ??
    stringField(asRecord(asRecord(payload.destination).oneTimeAddress), "address") ??
    stringField(firstRecord(payload.destinations), "destinationAddress")
  );
}

function validTxHash(txHash: string, chainId?: number): boolean {
  if (chainId === 501 || chainId === 101 || chainId === 102) return /^[1-9A-HJ-NP-Za-km-z]{32,96}$/.test(txHash);
  return /^0x[a-fA-F0-9]{64}$/.test(txHash);
}

function adapterForChain(chainId?: number): "bsc" | "ethereum" | "polygon" | "base" | "arbitrum" | "solana" | "fireblocks" {
  if (chainId === 56) return "bsc";
  if (chainId === 1) return "ethereum";
  if (chainId === 137) return "polygon";
  if (chainId === 8453) return "base";
  if (chainId === 42161) return "arbitrum";
  if (chainId === 501 || chainId === 101 || chainId === 102) return "solana";
  return "fireblocks";
}

function chainIdForAdapter(adapter: string): number {
  if (adapter === "bsc") return 56;
  if (adapter === "ethereum") return 1;
  if (adapter === "polygon") return 137;
  if (adapter === "base") return 8453;
  if (adapter === "arbitrum") return 42161;
  if (adapter === "solana") return 501;
  return Number(process.env.FIREBLOCKS_DEFAULT_CHAIN_ID ?? 0);
}

function fireblocksFeeLevel(): "LOW" | "MEDIUM" | "HIGH" {
  const value = String(process.env.FIREBLOCKS_FEE_LEVEL ?? "MEDIUM").toUpperCase();
  return value === "LOW" || value === "HIGH" ? value : "MEDIUM";
}

function assertCircuitClosed(): void {
  if (process.env.FIREBLOCKS_PAYOUT_CIRCUIT_BREAKER_OPEN === "1") {
    throw new Error("Fireblocks payout circuit breaker is open");
  }
}

function assertAssetId(value: string): void {
  if (!/^[A-Za-z0-9:_-]{2,80}$/.test(value)) throw new Error("Fireblocks assetId is invalid");
}

function assertDestination(value: string): void {
  if (!/^0x[a-fA-F0-9]{40}$/.test(value) && !/^[1-9A-HJ-NP-Za-km-z]{32,96}$/.test(value)) {
    throw new Error("destinationWallet must be a valid EVM or Solana-style wallet address");
  }
}

function assertPositiveDecimal(value: string, label: string): void {
  if (!/^\d+(\.\d+)?$/.test(value) || Number(value) <= 0) throw new Error(`${label} must be a positive decimal string`);
}

function stringField(value: Record<string, unknown>, field: string): string | undefined {
  const candidate = value[field];
  return typeof candidate === "string" && candidate.length > 0 ? candidate : undefined;
}

function numberField(value: Record<string, unknown>, field: string): number | undefined {
  const candidate = value[field];
  const parsed = typeof candidate === "number" ? candidate : typeof candidate === "string" ? Number(candidate) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : undefined;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function decimalToComparable(value: string): string {
  const [whole, fraction = ""] = String(value).split(".");
  return `${whole.replace(/^0+(?=\d)/, "")}.${fraction.replace(/0+$/, "")}`;
}

function redactedPayload(value: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(value, (key, inner) => (/secret|key|token|authorization|signature/i.test(key) ? "[redacted]" : inner))) as Record<string, unknown>;
}

function classifyFireblocksFailure(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  if (/auth|jwt|401/i.test(message)) return "FIREBLOCKS_AUTH";
  if (/liquidity/i.test(message)) return "INSUFFICIENT_REAL_LIQUIDITY";
  if (/confirmation|finality/i.test(message)) return "FIREBLOCKS_FINALITY";
  return "FIREBLOCKS_ERROR";
}

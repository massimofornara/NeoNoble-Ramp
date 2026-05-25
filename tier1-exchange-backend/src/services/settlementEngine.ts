import { createHmac, timingSafeEqual } from "node:crypto";
import type { DomainEvent, EventBus, ProviderWebhookInput } from "../core/types.js";
import type { EventStore, IdempotencyStore, SettlementProofStore } from "../core/store.js";
import { metrics } from "../core/observability.js";
import { settlementAdapterFor, type SettlementAdapter, type SettlementVerification } from "./settlementAdapters.js";
import { normalizeFailureReason } from "./smartRetryPolicy.js";

export class SettlementEngine {
  constructor(
    private readonly bus: EventBus,
    private readonly idempotency: IdempotencyStore,
    private readonly events: EventStore,
    private readonly settlementProofs: SettlementProofStore,
    private readonly webhookSecret = process.env.PROVIDER_WEBHOOK_SECRET || "local-provider-secret",
  ) {}

  registerConsumers(): void {
    this.bus.subscribe("execution.completed", "settlement-engine.execution-completed", async (event) => {
      try {
        if (isFireblocksManaged(event)) return;
        await this.initiateSettlement(event);
      } catch (error) {
        await this.publishSettlementFailed(event, error);
      }
    });
  }

  private async publishSettlementFailed(event: DomainEvent, error: unknown, partial?: Record<string, unknown>): Promise<void> {
    const classification = classifySettlementFailure(error);
    await this.bus.publish("settlement.failed", event.transactionId, {
      traceId: event.payload.traceId ?? asRecord(event.payload.metadata).traceId,
      accountId: event.payload.accountId,
      type: event.payload.type,
      provider: event.payload.provider,
      fromAsset: event.payload.fromAsset,
      toAsset: event.payload.toAsset,
      fromAmount: event.payload.fromAmount,
      expectedToAmount: event.payload.executedAmount,
      reason: classification,
      error: error instanceof Error ? error.message : String(error),
      metadata: event.payload.metadata ?? {},
      ...partial,
    });
    metrics.inc("exchange_settlement_failures_total", { reason: classification, type: String(event.payload.type) });
  }

  private async publishPendingConfirmation(event: DomainEvent, initiated: DomainEvent): Promise<void> {
    const alreadyPending = this.events.byTransaction(event.transactionId).some((candidate) => candidate.type === "settlement.pending_confirmation");
    if (alreadyPending) return;
    await this.bus.publish("settlement.pending_confirmation", event.transactionId, {
      traceId: event.payload.traceId ?? asRecord(event.payload.metadata).traceId,
      accountId: event.payload.accountId,
      type: event.payload.type,
      provider: event.payload.provider,
      txHash: initiated.payload.txHash,
      settlementId: initiated.payload.settlementId,
      adapter: initiated.payload.adapter,
      chainId: initiated.payload.chainId,
      requiredConfirmations: initiated.payload.requiredConfirmations,
      observedConfirmations: initiated.payload.observedConfirmations,
      receiptStatus: initiated.payload.receiptStatus,
      metadata: {
        confirmationSource: "chain-receipt-poller",
      },
    });
  }

  signWebhookPayload(rawBody: string, timestamp?: string, nonce?: string): string {
    const signedPayload = timestamp && nonce ? `${timestamp}.${nonce}.${rawBody}` : rawBody;
    return createHmac("sha256", this.webhookSecret).update(signedPayload).digest("hex");
  }

  assertWebhookSignature(rawBody: string, signature: string | undefined, timestamp?: string, nonce?: string): void {
    if (!signature) throw new Error("Missing x-provider-signature header");
    const expected = this.signWebhookPayload(rawBody, timestamp, nonce);
    const left = Buffer.from(signature, "hex");
    const right = Buffer.from(expected, "hex");
    if (left.length !== right.length || !timingSafeEqual(left, right)) {
      throw new Error("Invalid provider webhook signature");
    }
  }

  async ingestProviderWebhook(input: ProviderWebhookInput): Promise<{ transactionId: string; status: "accepted"; duplicate?: boolean }> {
    const existing = this.idempotency.get<{ transactionId: string; status: "accepted"; duplicate?: boolean }>(
      "provider.webhook",
      input.idempotencyKey,
    );
    if (existing) return { ...existing, duplicate: true };

    if (input.status !== "confirmed") {
      throw new Error("Only confirmed provider webhooks advance settlement in this architecture");
    }
    if (!input.providerReference) {
      throw new Error("providerReference is required");
    }
    const initiated = this.findInitiated(input.transactionId);
    const settlementId = input.settlementId ?? String(initiated.payload.settlementId);
    const txHash = input.txHash ?? String(initiated.payload.txHash);
    if (settlementId !== String(initiated.payload.settlementId)) {
      throw new Error("Webhook settlementId does not match initiated settlement proof");
    }
    if (txHash !== String(initiated.payload.txHash)) {
      throw new Error("Webhook txHash does not match initiated settlement proof");
    }
    const verification = await settlementAdapterFor(String(initiated.payload.adapter ?? initiated.payload.provider)).verify({
      txHash,
      transactionId: input.transactionId,
      settlementId,
    });
    if (!verification.valid) {
      throw new Error(
        `Settlement finality not reached: receiptStatus=${verification.receiptStatus}, confirmations=${verification.observedConfirmations}/${verification.requiredConfirmations}`,
      );
    }
    const proof = await this.settlementProofs.append({
      transactionId: input.transactionId,
      settlementId,
      txHash,
      adapter: verification.adapter,
      chainId: verification.chainId,
      status: "confirmed",
      requiredConfirmations: verification.requiredConfirmations,
      observedConfirmations: verification.observedConfirmations,
      blockNumber: verification.blockNumber,
      receiptStatus: verification.receiptStatus,
      providerReference: input.providerReference || verification.providerReference,
      payload: {
        ...verification.payload,
        webhookMetadata: input.metadata ?? {},
      },
    });
    metrics.observe("exchange_settlement_latency_ms", Date.now() - Date.parse(initiated.timestamp), {
      adapter: verification.adapter,
    });

    await this.publishPendingConfirmation(initiated, initiated);
    await this.bus.publish("settlement.confirmed", input.transactionId, {
      traceId: initiated.payload.traceId,
      providerReference: input.providerReference,
      settlementId,
      txHash,
      adapter: verification.adapter,
      chainId: verification.chainId,
      requiredConfirmations: verification.requiredConfirmations,
      observedConfirmations: verification.observedConfirmations,
      blockNumber: verification.blockNumber,
      settlementProofHash: proof.currentHash,
      metadata: input.metadata ?? {},
    });

    return this.idempotency.set("provider.webhook", input.idempotencyKey, {
      transactionId: input.transactionId,
      status: "accepted",
    });
  }

  private async initiateSettlement(event: DomainEvent): Promise<void> {
    const existing = this.idempotency.get<{ transactionId: string; status: "pending" | "confirmed" | "failed"; txHash?: string }>(
      "settlement.execution.completed",
      event.eventId,
    );
    if (existing) return;

    const adapter = settlementAdapterFor(String(event.payload.provider ?? process.env.DEFAULT_SETTLEMENT_ADAPTER ?? process.env.SETTLEMENT_ADAPTER ?? ""));
    const settlementId = `set_${event.eventId}`;

    const broadcast = await adapter.broadcast(event);
    const initiatedProof = await this.settlementProofs.append({
      transactionId: event.transactionId,
      settlementId,
      txHash: broadcast.txHash,
      adapter: broadcast.adapter,
      chainId: broadcast.chainId,
      status: "initiated",
      requiredConfirmations: broadcast.requiredConfirmations,
      observedConfirmations: broadcast.observedConfirmations,
      blockNumber: broadcast.blockNumber,
      receiptStatus: broadcast.receiptStatus,
      payload: broadcast.payload,
    });
    const initiated = await this.bus.publish("settlement.initiated", event.transactionId, {
      traceId: event.payload.traceId ?? asRecord(event.payload.metadata).traceId,
      txHash: broadcast.txHash,
      provider: event.payload.provider,
      adapter: broadcast.adapter,
      chainId: broadcast.chainId,
      settlementId,
      accountId: event.payload.accountId,
      asset: event.payload.toAsset,
      amount: event.payload.executedAmount,
      executionReference: event.payload.executionReference,
      requiredConfirmations: broadcast.requiredConfirmations,
      observedConfirmations: broadcast.observedConfirmations,
      blockNumber: broadcast.blockNumber,
      receiptStatus: broadcast.receiptStatus,
      settlementProofHash: initiatedProof.currentHash,
      valuation: event.payload.valuation ?? {},
    });

    await this.publishPendingConfirmation(event, initiated);
    let verification = await adapter.waitForFinality({
      txHash: broadcast.txHash,
      transactionId: event.transactionId,
      settlementId,
    });
    if (!verification.valid) {
      const replacement = await this.tryReplacementBroadcast(adapter, event, settlementId, broadcast, verification);
      if (replacement) {
        verification = replacement;
      }
    }

    if (!verification.valid) {
      if (verification.receiptStatus === "failed") {
        const failedProof = await this.settlementProofs.append({
          transactionId: event.transactionId,
          settlementId,
          txHash: verification.txHash,
          adapter: verification.adapter,
          chainId: verification.chainId,
          status: "failed",
          requiredConfirmations: verification.requiredConfirmations,
          observedConfirmations: verification.observedConfirmations,
          blockNumber: verification.blockNumber,
          receiptStatus: verification.receiptStatus,
          providerReference: verification.providerReference,
          payload: verification.payload,
        });
        await this.publishSettlementFailed(event, new Error("Settlement transaction receipt failed"), {
          txHash: verification.txHash,
          settlementId,
          adapter: verification.adapter,
          chainId: verification.chainId,
          settlementProofHash: failedProof.currentHash,
        });
        await this.idempotency.set("settlement.execution.completed", event.eventId, {
          transactionId: event.transactionId,
          status: "failed",
          txHash: verification.txHash,
        });
        return;
      }
      await this.idempotency.set("settlement.execution.completed", event.eventId, {
        transactionId: event.transactionId,
        status: "pending",
        txHash: verification.txHash,
      });
      return;
    }

    const confirmedProof = await this.settlementProofs.append({
      transactionId: event.transactionId,
      settlementId,
      txHash: verification.txHash,
      adapter: verification.adapter,
      chainId: verification.chainId,
      status: "confirmed",
      requiredConfirmations: verification.requiredConfirmations,
      observedConfirmations: verification.observedConfirmations,
      blockNumber: verification.blockNumber,
      receiptStatus: verification.receiptStatus,
      providerReference: verification.providerReference,
      payload: {
        ...broadcast.payload,
        ...verification.payload,
        confirmationSource: "settlement-engine-finality",
      },
    });
    metrics.observe("exchange_settlement_latency_ms", Date.now() - Date.parse(event.timestamp), {
      adapter: verification.adapter,
    });
    await this.bus.publish("settlement.confirmed", event.transactionId, {
      traceId: event.payload.traceId ?? asRecord(event.payload.metadata).traceId,
      providerReference: verification.providerReference,
      settlementId,
      txHash: verification.txHash,
      adapter: verification.adapter,
      chainId: verification.chainId,
      requiredConfirmations: verification.requiredConfirmations,
      observedConfirmations: verification.observedConfirmations,
      blockNumber: verification.blockNumber,
      settlementProofHash: confirmedProof.currentHash,
      metadata: {
        confirmationSource: "settlement-engine-finality",
      },
    });
    await this.idempotency.set("settlement.execution.completed", event.eventId, {
      transactionId: event.transactionId,
      status: "confirmed",
      txHash: verification.txHash,
    });
  }

  private findInitiated(transactionId: string): DomainEvent {
    const initiated = this.events.byTransaction(transactionId).find((event) => event.type === "settlement.initiated");
    if (!initiated) throw new Error("Settlement was not initiated for transaction");
    return initiated;
  }

  private async tryReplacementBroadcast(
    adapter: SettlementAdapter,
    event: DomainEvent,
    settlementId: string,
    broadcast: { txHash: string; payload: Record<string, unknown> },
    verification: { valid: boolean; payload: Record<string, unknown> },
  ): Promise<SettlementVerification | undefined> {
    if (process.env.ENABLE_STUCK_TX_REPLACEMENT !== "1") return undefined;
    const watchtower = asRecord(verification.payload.watchtower);
    if (watchtower.replacementRequired !== true || typeof adapter.replaceStuckTransaction !== "function") return undefined;
    const nonce = Number(broadcast.payload.nonce);
    if (!Number.isInteger(nonce) || nonce < 0) return undefined;
    const replacement = await adapter.replaceStuckTransaction(event, {
      txHash: broadcast.txHash,
      transactionId: event.transactionId,
      settlementId,
      nonce,
      previousFeeStrategy: asRecord(broadcast.payload.feeStrategy),
    });
    const replacementProof = await this.settlementProofs.append({
      transactionId: event.transactionId,
      settlementId,
      txHash: replacement.txHash,
      adapter: replacement.adapter,
      chainId: replacement.chainId,
      status: "initiated",
      requiredConfirmations: replacement.requiredConfirmations,
      observedConfirmations: replacement.observedConfirmations,
      blockNumber: replacement.blockNumber,
      receiptStatus: replacement.receiptStatus,
      payload: replacement.payload,
    });
    await this.bus.publish("settlement.replacement_broadcast", event.transactionId, {
      traceId: event.payload.traceId ?? asRecord(event.payload.metadata).traceId,
      txHash: replacement.txHash,
      replacesTxHash: broadcast.txHash,
      provider: event.payload.provider,
      adapter: replacement.adapter,
      chainId: replacement.chainId,
      settlementId,
      accountId: event.payload.accountId,
      asset: event.payload.toAsset,
      amount: event.payload.executedAmount,
      requiredConfirmations: replacement.requiredConfirmations,
      observedConfirmations: replacement.observedConfirmations,
      receiptStatus: replacement.receiptStatus,
      settlementProofHash: replacementProof.currentHash,
      metadata: {
        confirmationSource: "watchtower-stuck-tx-replacement",
      },
    });
    return adapter.waitForFinality({
      txHash: replacement.txHash,
      transactionId: event.transactionId,
      settlementId,
    });
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function isFireblocksManaged(event: DomainEvent): boolean {
  const metadata = asRecord(event.payload.metadata);
  return String(event.payload.provider ?? "").toLowerCase() === "fireblocks" || metadata.settlementRail === "fireblocks-managed";
}

function classifySettlementFailure(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  if (/timeout|not reached|pending|confirmations/i.test(message)) return "SETTLEMENT_TIMEOUT";
  return normalizeFailureReason(error);
}

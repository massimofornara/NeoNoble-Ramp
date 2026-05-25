import "../core/env.js";

import { createTier1ExchangeApp } from "../app.js";
import type { DomainEvent, SettlementProof } from "../core/types.js";
import { settlementAdapterFor, type SettlementAdapter, type SettlementVerification } from "../services/settlementAdapters.js";
import { TreasurySigner, type TreasuryTransactionRequest } from "../services/treasurySigner.js";

interface RecoveryResult {
  transactionId: string;
  settlementId?: string;
  originalTxHash?: string;
  replacementTxHash?: string;
  status: "confirmed" | "replacement_broadcast" | "pending" | "blocked" | "failed" | "skipped";
  reason?: string;
  receiptStatus?: string;
  observedConfirmations?: number;
  requiredConfirmations?: number;
  replacementRequired?: boolean;
  integrity?: boolean;
}

async function main(): Promise<void> {
  if (process.env.RECOVER_STUCK_SETTLEMENTS !== "1") {
    throw new Error("RECOVER_STUCK_SETTLEMENTS=1 is required because this can broadcast real replacement transactions");
  }

  const app = createTier1ExchangeApp();
  await app.store.ready();
  const filter = new Set((process.env.RECOVER_TRANSACTION_IDS ?? "").split(",").map((value) => value.trim()).filter(Boolean));
  const transactionIds = [...new Set(app.store.events.all().map((event) => event.transactionId))].filter((transactionId) => filter.size === 0 || filter.has(transactionId));
  const results: RecoveryResult[] = [];

  for (const transactionId of transactionIds) {
    const events = app.store.events.byTransaction(transactionId);
    if (!events.some((event) => event.type === "settlement.initiated")) continue;
    if (events.some((event) => event.type === "settlement.confirmed")) {
      results.push({ transactionId, status: "skipped", reason: "already settlement.confirmed" });
      continue;
    }
    if (events.some((event) => event.type === "settlement.failed" || event.type === "execution.failed")) {
      results.push({ transactionId, status: "skipped", reason: "terminal failure exists" });
      continue;
    }
    results.push(await recoverTransaction(app, transactionId, events));
    await app.bus.drain();
  }

  const summary = {
    mode: "recover-stuck-settlements",
    generatedAt: new Date().toISOString(),
    guardrails: {
      noSyntheticReceipt: true,
      noForcedFinality: true,
      confirmationDepthRequired: true,
      replacementRequiresWatchtowerSignal: true,
    },
    totals: {
      checked: results.length,
      confirmed: results.filter((result) => result.status === "confirmed").length,
      replacementBroadcast: results.filter((result) => result.status === "replacement_broadcast").length,
      pending: results.filter((result) => result.status === "pending").length,
      blocked: results.filter((result) => result.status === "blocked").length,
      failed: results.filter((result) => result.status === "failed").length,
      skipped: results.filter((result) => result.status === "skipped").length,
    },
    results,
  };
  console.log(JSON.stringify(summary, null, 2));
  if (summary.totals.failed > 0 || summary.totals.blocked > 0) process.exitCode = 1;
}

async function recoverTransaction(app: ReturnType<typeof createTier1ExchangeApp>, transactionId: string, events: DomainEvent[]): Promise<RecoveryResult> {
  const completed = latest(events, "execution.completed");
  const initiated = latest(events, "settlement.initiated");
  if (!completed || !initiated) return { transactionId, status: "blocked", reason: "execution.completed or settlement.initiated missing" };

  const settlementId = String(initiated.payload.settlementId ?? "");
  const originalTxHash = String(initiated.payload.txHash ?? "");
  const adapterName = String(initiated.payload.adapter ?? process.env.SETTLEMENT_ADAPTER ?? "");
  const adapter = settlementAdapterFor(adapterName);
  const proofs = app.store.settlementProofs.byTransaction(transactionId);
  const originalProof = proofs.find((proof) => proof.settlementId === settlementId && proof.txHash === originalTxHash && proof.status === "initiated");
  const replacementEvent = latest(events, "settlement.replacement_broadcast");
  const replacementTxHash = stringPayload(replacementEvent, "txHash");

  const activeTxHash = replacementTxHash ?? originalTxHash;
  const activeVerification = await adapter.verify({ txHash: activeTxHash, transactionId, settlementId, firstSeenAt: initiated.timestamp });
  if (activeVerification.valid) {
    await confirmSettlement(app, completed, initiated, activeVerification, replacementTxHash ? "replacement-finality" : "original-finality");
    const report = await app.reconciliationEngine.reconcile(transactionId);
    return {
      transactionId,
      settlementId,
      originalTxHash,
      replacementTxHash,
      status: "confirmed",
      receiptStatus: activeVerification.receiptStatus,
      observedConfirmations: activeVerification.observedConfirmations,
      requiredConfirmations: activeVerification.requiredConfirmations,
      integrity: report.integrity,
    };
  }

  const watchtower = asRecord(activeVerification.payload.watchtower);
  const replacementRequired = watchtower.replacementRequired === true;
  if (replacementTxHash) {
    return {
      transactionId,
      settlementId,
      originalTxHash,
      replacementTxHash,
      status: "pending",
      reason: "replacement already broadcast but finality not reached",
      receiptStatus: activeVerification.receiptStatus,
      observedConfirmations: activeVerification.observedConfirmations,
      requiredConfirmations: activeVerification.requiredConfirmations,
      replacementRequired,
    };
  }
  if (!replacementRequired) {
    return {
      transactionId,
      settlementId,
      originalTxHash,
      status: "pending",
      reason: "watchtower does not require replacement yet",
      receiptStatus: activeVerification.receiptStatus,
      observedConfirmations: activeVerification.observedConfirmations,
      requiredConfirmations: activeVerification.requiredConfirmations,
      replacementRequired,
    };
  }
  if (typeof adapter.replaceStuckTransaction !== "function") {
    return { transactionId, settlementId, originalTxHash, status: "blocked", reason: "adapter does not support stuck transaction replacement", replacementRequired };
  }
  const nonce = Number(originalProof?.payload.nonce);
  if (!Number.isInteger(nonce) || nonce < 0) {
    return { transactionId, settlementId, originalTxHash, status: "blocked", reason: "original settlement proof missing nonce", replacementRequired };
  }

  try {
    const replacement = await adapter.replaceStuckTransaction(completed, {
      txHash: originalTxHash,
      transactionId,
      settlementId,
      nonce,
      previousFeeStrategy: asRecord(originalProof?.payload.feeStrategy),
    });
    const replacementProof = await app.store.settlementProofs.append({
      transactionId,
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
    await app.bus.publish("settlement.replacement_broadcast", transactionId, {
      traceId: completed.payload.traceId ?? asRecord(completed.payload.metadata).traceId,
      txHash: replacement.txHash,
      replacesTxHash: originalTxHash,
      provider: completed.payload.provider,
      adapter: replacement.adapter,
      chainId: replacement.chainId,
      settlementId,
      accountId: completed.payload.accountId,
      asset: completed.payload.toAsset,
      amount: completed.payload.executedAmount,
      requiredConfirmations: replacement.requiredConfirmations,
      observedConfirmations: replacement.observedConfirmations,
      receiptStatus: replacement.receiptStatus,
      settlementProofHash: replacementProof.currentHash,
      metadata: {
        confirmationSource: "manual-watchtower-stuck-tx-replacement",
      },
    });
    const verification = await adapter.waitForFinality({
      txHash: replacement.txHash,
      transactionId,
      settlementId,
    });
    if (!verification.valid) {
      return {
        transactionId,
        settlementId,
        originalTxHash,
        replacementTxHash: replacement.txHash,
        status: "replacement_broadcast",
        reason: "replacement broadcast, finality not reached yet",
        receiptStatus: verification.receiptStatus,
        observedConfirmations: verification.observedConfirmations,
        requiredConfirmations: verification.requiredConfirmations,
        replacementRequired,
      };
    }
    await confirmSettlement(app, completed, initiated, verification, "replacement-finality");
    const report = await app.reconciliationEngine.reconcile(transactionId);
    return {
      transactionId,
      settlementId,
      originalTxHash,
      replacementTxHash: replacement.txHash,
      status: "confirmed",
      receiptStatus: verification.receiptStatus,
      observedConfirmations: verification.observedConfirmations,
      requiredConfirmations: verification.requiredConfirmations,
      integrity: report.integrity,
    };
  } catch (error) {
    if (process.env.ALLOW_ORPHAN_FINAL_REBROADCAST === "1" && isNonceExpired(error)) {
      return rebroadcastOrphanedFinalSettlement(app, adapter, completed, initiated, originalTxHash, originalProof, error);
    }
    return {
      transactionId,
      settlementId,
      originalTxHash,
      status: "failed",
      reason: error instanceof Error ? error.message : String(error),
      replacementRequired,
    };
  }
}

async function rebroadcastOrphanedFinalSettlement(
  app: ReturnType<typeof createTier1ExchangeApp>,
  adapter: SettlementAdapter,
  completed: DomainEvent,
  initiated: DomainEvent,
  originalTxHash: string,
  originalProof: SettlementProof | undefined,
  cause: unknown,
): Promise<RecoveryResult> {
  const transactionId = completed.transactionId;
  const settlementId = String(initiated.payload.settlementId ?? "");
  const request = transactionRequestFrom(asRecord(asRecord(completed.payload.metadata).settlementTransaction));
  const signer = signerFor(adapter.name);
  const signed = await signer.signAndBroadcast(request);
  const replacementProof = await app.store.settlementProofs.append({
    transactionId,
    settlementId,
    txHash: signed.txHash,
    adapter: adapter.name,
    chainId: Number(initiated.payload.chainId ?? chainIdFor(adapter.name)),
    status: "initiated",
    requiredConfirmations: Number(initiated.payload.requiredConfirmations ?? confirmationDepthFor(adapter.name)),
    observedConfirmations: 0,
    receiptStatus: "pending",
    payload: {
      broadcastMode: "orphaned-final-rebroadcast",
      orphanedTxHash: originalTxHash,
      orphanedNonce: originalProof?.payload.nonce,
      cause: cause instanceof Error ? cause.message : String(cause),
      nonce: signed.nonce,
      gasLimit: signed.gasLimit,
      feeStrategy: signed.feeStrategy,
      treasuryAddress: process.env.TREASURY_ADDRESS,
    },
  });
  await app.bus.publish("settlement.replacement_broadcast", transactionId, {
    traceId: completed.payload.traceId ?? asRecord(completed.payload.metadata).traceId,
    txHash: signed.txHash,
    replacesTxHash: originalTxHash,
    provider: completed.payload.provider,
    adapter: adapter.name,
    chainId: Number(initiated.payload.chainId ?? chainIdFor(adapter.name)),
    settlementId,
    accountId: completed.payload.accountId,
    asset: completed.payload.toAsset,
    amount: completed.payload.executedAmount,
    requiredConfirmations: Number(initiated.payload.requiredConfirmations ?? confirmationDepthFor(adapter.name)),
    observedConfirmations: 0,
    receiptStatus: "pending",
    settlementProofHash: replacementProof.currentHash,
    metadata: {
      confirmationSource: "orphaned-final-rebroadcast",
      orphanedNonce: originalProof?.payload.nonce,
    },
  });
  const verification = await adapter.waitForFinality({
    txHash: signed.txHash,
    transactionId,
    settlementId,
  });
  if (!verification.valid) {
    return {
      transactionId,
      settlementId,
      originalTxHash,
      replacementTxHash: signed.txHash,
      status: "replacement_broadcast",
      reason: "orphaned final slice rebroadcast, finality not reached yet",
      receiptStatus: verification.receiptStatus,
      observedConfirmations: verification.observedConfirmations,
      requiredConfirmations: verification.requiredConfirmations,
      replacementRequired: false,
    };
  }
  await confirmSettlement(app, completed, initiated, verification, "orphaned-final-rebroadcast-finality");
  const report = await app.reconciliationEngine.reconcile(transactionId);
  return {
    transactionId,
    settlementId,
    originalTxHash,
    replacementTxHash: signed.txHash,
    status: "confirmed",
    receiptStatus: verification.receiptStatus,
    observedConfirmations: verification.observedConfirmations,
    requiredConfirmations: verification.requiredConfirmations,
    integrity: report.integrity,
  };
}

async function confirmSettlement(
  app: ReturnType<typeof createTier1ExchangeApp>,
  completed: DomainEvent,
  initiated: DomainEvent,
  verification: SettlementVerification,
  confirmationSource: string,
): Promise<SettlementProof> {
  const transactionId = completed.transactionId;
  if (app.store.events.byTransaction(transactionId).some((event) => event.type === "settlement.confirmed")) {
    const existing = app.store.settlementProofs.latestConfirmed(transactionId);
    if (existing) return existing;
  }
  const settlementId = String(initiated.payload.settlementId);
  const proof = await app.store.settlementProofs.append({
    transactionId,
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
      ...verification.payload,
      confirmationSource,
    },
  });
  await app.bus.publish("settlement.confirmed", transactionId, {
    traceId: completed.payload.traceId ?? asRecord(completed.payload.metadata).traceId,
    providerReference: verification.providerReference,
    settlementId,
    txHash: verification.txHash,
    adapter: verification.adapter,
    chainId: verification.chainId,
    requiredConfirmations: verification.requiredConfirmations,
    observedConfirmations: verification.observedConfirmations,
    blockNumber: verification.blockNumber,
    settlementProofHash: proof.currentHash,
    metadata: {
      confirmationSource,
    },
  });
  await app.bus.drain();
  return proof;
}

function latest(events: DomainEvent[], type: DomainEvent["type"]): DomainEvent | undefined {
  return events.filter((event) => event.type === type).at(-1);
}

function stringPayload(event: DomainEvent | undefined, key: string): string | undefined {
  const value = event?.payload[key];
  return value === undefined || value === null ? undefined : String(value);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function isNonceExpired(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /nonce too low|nonce has already been used|NONCE_EXPIRED/i.test(message);
}

function signerFor(adapter: SettlementAdapter["name"]): TreasurySigner {
  if (adapter === "bsc") {
    const rpcUrl = process.env.BSC_RPC_URL;
    if (!rpcUrl) throw new Error("BSC_RPC_URL is required for orphaned final rebroadcast");
    return new TreasurySigner(rpcUrl, Number(process.env.BSC_CHAIN_ID ?? process.env.CHAIN_ID ?? 56));
  }
  const rpcUrl = process.env.ETHEREUM_RPC_URL;
  if (!rpcUrl) throw new Error("ETHEREUM_RPC_URL is required for orphaned final rebroadcast");
  return new TreasurySigner(rpcUrl, Number(process.env.ETHEREUM_CHAIN_ID ?? 1));
}

function chainIdFor(adapter: SettlementAdapter["name"]): number {
  return adapter === "bsc" ? Number(process.env.BSC_CHAIN_ID ?? process.env.CHAIN_ID ?? 56) : Number(process.env.ETHEREUM_CHAIN_ID ?? 1);
}

function confirmationDepthFor(adapter: SettlementAdapter["name"]): number {
  return adapter === "bsc"
    ? Number(process.env.BSC_CONFIRMATION_DEPTH ?? process.env.CONFIRMATION_DEPTH ?? 15)
    : Number(process.env.ETHEREUM_CONFIRMATION_DEPTH ?? 64);
}

function transactionRequestFrom(metadata: Record<string, unknown>): TreasuryTransactionRequest {
  const to = String(metadata.to ?? "");
  const data = String(metadata.data ?? "0x");
  if (!/^0x[a-fA-F0-9]{40}$/.test(to)) throw new Error("orphaned final rebroadcast requires settlementTransaction.to");
  if (!/^0x([a-fA-F0-9]{2})*$/.test(data)) throw new Error("orphaned final rebroadcast settlementTransaction.data must be hex bytes");
  return {
    to,
    data,
    valueWei: optionalString(metadata.valueWei) ?? "0",
    gasLimit: optionalString(metadata.gasLimit),
    gasPriceWei: optionalString(metadata.gasPriceWei),
    maxFeePerGasWei: optionalString(metadata.maxFeePerGasWei),
    maxPriorityFeePerGasWei: optionalString(metadata.maxPriorityFeePerGasWei),
  };
}

function optionalString(value: unknown): string | undefined {
  return value === undefined || value === null || value === "" ? undefined : String(value);
}

main().catch((error) => {
  console.error(JSON.stringify({ level: "error", component: "recover-stuck-settlements", error: error instanceof Error ? error.message : String(error) }));
  process.exitCode = 1;
});

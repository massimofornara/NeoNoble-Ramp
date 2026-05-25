import type { DomainEvent } from "../core/types.js";
import { TreasurySigner, type TreasuryTransactionRequest } from "./treasurySigner.js";
import { RpcQuorum } from "./rpcQuorum.js";
import { WatchtowerService } from "./watchtowerService.js";

export type SettlementAdapterName = "bsc" | "ethereum";

export interface SettlementInitiation {
  adapter: SettlementAdapterName;
  chainId: number;
  txHash: string;
  requiredConfirmations: number;
  observedConfirmations: number;
  blockNumber?: number;
  receiptStatus: "success" | "failed" | "pending";
  payload: Record<string, unknown>;
}

export type SettlementBroadcast = SettlementInitiation;

export interface SettlementVerification extends SettlementInitiation {
  valid: boolean;
  providerReference: string;
}

export interface SettlementAdapter {
  readonly name: SettlementAdapterName;
  broadcast(event: DomainEvent): Promise<SettlementBroadcast>;
  replaceStuckTransaction?(event: DomainEvent, input: { txHash: string; transactionId: string; settlementId: string; nonce: number; previousFeeStrategy?: Record<string, unknown> }): Promise<SettlementBroadcast>;
  waitForFinality(input: { txHash: string; transactionId: string; settlementId: string; firstSeenAt?: string }): Promise<SettlementVerification>;
  verify(input: { txHash: string; transactionId: string; settlementId: string; firstSeenAt?: string }): Promise<SettlementVerification>;
  nextNonce?(address: string): Promise<number>;
}

export class JsonRpcChainSettlementAdapter implements SettlementAdapter {
  constructor(
    readonly name: "bsc" | "ethereum",
    private readonly rpcUrl: string,
    private readonly chainId: number,
    private readonly requiredConfirmations: number,
  ) {}

  async initiate(event: DomainEvent): Promise<SettlementInitiation> {
    const broadcast = await this.broadcast(event);
    const verified = await this.waitForFinality({
      txHash: broadcast.txHash,
      transactionId: event.transactionId,
      settlementId: `set_${event.eventId}`,
    });
    return {
      ...verified,
      payload: {
        ...broadcast.payload,
        ...verified.payload,
      },
    };
  }

  async broadcast(event: DomainEvent): Promise<SettlementBroadcast> {
    const metadata = asRecord(event.payload.metadata);
    const preSettlementTransactions = transactionRequestsFrom(metadata.preSettlementTransactions);
    const settlementTransaction = asRecord(metadata.settlementTransaction);
    const request = transactionRequestFrom(settlementTransaction);
    const signer = new TreasurySigner(this.rpcUrl, this.chainId);
    const preSettlementTxs: Array<Record<string, unknown>> = [];
    for (const [index, preRequest] of preSettlementTransactions.entries()) {
      const signedPre = await signer.signAndBroadcast(preRequest);
      const verifiedPre = await this.waitForFinality({
        txHash: signedPre.txHash,
        transactionId: event.transactionId,
        settlementId: `pre_${event.eventId}_${index}`,
      });
      if (!verifiedPre.valid) {
        throw new Error(
          `Pre-settlement transaction ${index} finality not reached: receiptStatus=${verifiedPre.receiptStatus}, confirmations=${verifiedPre.observedConfirmations}/${verifiedPre.requiredConfirmations}`,
        );
      }
      preSettlementTxs.push({
        index,
        txHash: signedPre.txHash,
        nonce: signedPre.nonce,
        gasLimit: signedPre.gasLimit,
        feeStrategy: signedPre.feeStrategy,
        blockNumber: verifiedPre.blockNumber,
        observedConfirmations: verifiedPre.observedConfirmations,
        requiredConfirmations: verifiedPre.requiredConfirmations,
        receiptStatus: verifiedPre.receiptStatus,
      });
    }
    const signed = await signer.signAndBroadcast(request);
    const txHash = signed.txHash;
    const broadcastPayload: Record<string, unknown> = {
      broadcastMode: "treasury-signer",
      preSettlementTxs,
      nonce: signed.nonce,
      gasLimit: signed.gasLimit,
      feeStrategy: signed.feeStrategy,
      treasuryAddress: process.env.TREASURY_ADDRESS,
    };
    return {
      adapter: this.name,
      chainId: this.chainId,
      txHash,
      requiredConfirmations: this.requiredConfirmations,
      observedConfirmations: 0,
      receiptStatus: "pending",
      payload: broadcastPayload,
    };
  }

  async waitForFinality(input: { txHash: string; transactionId: string; settlementId: string; firstSeenAt?: string }): Promise<SettlementVerification> {
    const attempts = Number(process.env.SETTLEMENT_RECEIPT_POLL_ATTEMPTS ?? 12);
    const intervalMs = Number(process.env.SETTLEMENT_RECEIPT_POLL_INTERVAL_MS ?? 5000);
    const firstSeenAt = input.firstSeenAt ?? new Date().toISOString();
    let latest = await this.verify({ ...input, firstSeenAt });
    for (let attempt = 1; attempt < attempts && !latest.valid; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
      latest = await this.verify({ ...input, firstSeenAt });
    }
    return latest;
  }

  async replaceStuckTransaction(
    event: DomainEvent,
    input: { txHash: string; transactionId: string; settlementId: string; nonce: number; previousFeeStrategy?: Record<string, unknown> },
  ): Promise<SettlementBroadcast> {
    const metadata = asRecord(event.payload.metadata);
    const request = {
      ...transactionRequestFrom(asRecord(metadata.settlementTransaction)),
      nonce: input.nonce,
      ...escalatedFee(input.previousFeeStrategy),
    };
    const signer = new TreasurySigner(this.rpcUrl, this.chainId);
    const signed = await signer.signAndBroadcast(request);
    return {
      adapter: this.name,
      chainId: this.chainId,
      txHash: signed.txHash,
      requiredConfirmations: this.requiredConfirmations,
      observedConfirmations: 0,
      receiptStatus: "pending",
      payload: {
        broadcastMode: "treasury-signer-replacement",
        replacementFor: input.txHash,
        nonce: signed.nonce,
        gasLimit: signed.gasLimit,
        feeStrategy: signed.feeStrategy,
        treasuryAddress: process.env.TREASURY_ADDRESS,
      },
    };
  }

  async broadcastSettlementTransaction(request: TreasuryTransactionRequest): Promise<SettlementVerification> {
    const signer = new TreasurySigner(this.rpcUrl, this.chainId);
    const signed = await signer.signAndBroadcast(request);
    return this.waitForFinality({
      txHash: signed.txHash,
      transactionId: `manual-${signed.txHash}`,
      settlementId: `manual-${signed.nonce}`,
    });
  }

  async verify(input: { txHash: string; transactionId: string; settlementId: string; firstSeenAt?: string }): Promise<SettlementVerification> {
    if (process.env.SETTLEMENT_WATCHTOWER_ENABLED !== "0") {
      const extraUrls = process.env[`${this.name.toUpperCase()}_RPC_URLS`]?.split(",").map((value) => value.trim()).filter(Boolean) ?? [];
      const watchtower = new WatchtowerService(new RpcQuorum([this.rpcUrl, ...extraUrls]));
      const observed = await watchtower.verify(input.txHash, input.firstSeenAt ?? new Date().toISOString(), this.requiredConfirmations);
      return this.verification(
        input,
        observed.observedConfirmations,
        observed.blockNumber,
        observed.receiptStatus,
        observed.valid,
        {
          watchtower: observed,
        },
      );
    }
    const receipt = await this.rpc<Record<string, unknown> | null>("eth_getTransactionReceipt", [input.txHash]);
    if (!receipt) {
      return this.verification(input, 0, undefined, "pending", false, { receipt: null });
    }
    const latestBlock = hexToNumber(await this.rpc<string>("eth_blockNumber", []));
    const blockNumber = hexToNumber(String(receipt.blockNumber));
    const observedConfirmations = Math.max(0, latestBlock - blockNumber + 1);
    const success = String(receipt.status).toLowerCase() === "0x1";
    return this.verification(input, observedConfirmations, blockNumber, success ? "success" : "failed", success && observedConfirmations >= this.requiredConfirmations, {
      receipt,
      latestBlock,
    });
  }

  async nextNonce(address: string): Promise<number> {
    return hexToNumber(await this.rpc<string>("eth_getTransactionCount", [address, "pending"]));
  }

  private verification(
    input: { txHash: string; transactionId: string; settlementId: string },
    observedConfirmations: number,
    blockNumber: number | undefined,
    receiptStatus: "success" | "failed" | "pending",
    valid: boolean,
    payload: Record<string, unknown>,
  ): SettlementVerification {
    return {
      adapter: this.name,
      chainId: this.chainId,
      txHash: input.txHash,
      requiredConfirmations: this.requiredConfirmations,
      observedConfirmations,
      blockNumber,
      receiptStatus,
      valid,
      providerReference: `${this.name}:${input.settlementId}:${input.txHash}`,
      payload,
    };
  }

  private async rpc<T>(method: string, params: unknown[]): Promise<T> {
    const response = await fetch(this.rpcUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: `${Date.now()}:${method}`,
        method,
        params,
      }),
    });
    const body = (await response.json()) as { result?: T; error?: { message?: string } };
    if (!response.ok || body.error) {
      throw new Error(body.error?.message ?? `JSON-RPC ${method} failed with ${response.status}`);
    }
    return body.result as T;
  }
}

export function settlementAdapterFor(provider: string | undefined): SettlementAdapter {
  const executionMode = String(process.env.BLOCKCHAIN_EXECUTION_MODE ?? "deterministic").toLowerCase();
  const providerName = String(provider ?? "").toLowerCase();
  const configuredAdapter = process.env.SETTLEMENT_ADAPTER ?? process.env.DEFAULT_SETTLEMENT_ADAPTER;
  const requested = String(providerName === "real" || executionMode === "real" ? configuredAdapter ?? "" : provider ?? configuredAdapter ?? "").toLowerCase();
  if (providerName === "real" && executionMode !== "real") {
    throw new Error("Real settlement requests require BLOCKCHAIN_EXECUTION_MODE=real; placeholder fallback is disabled for provider=real");
  }
  if (executionMode === "real" && !["bsc", "ethereum", "eth"].includes(requested)) {
    throw new Error("BLOCKCHAIN_EXECUTION_MODE=real requires SETTLEMENT_ADAPTER=bsc or SETTLEMENT_ADAPTER=ethereum; placeholder settlement is disabled");
  }
  if (requested === "bsc") {
    const rpcUrl = process.env.BSC_RPC_URL;
    if (!rpcUrl) throw new Error("BSC_RPC_URL is required for BSC settlement adapter");
    return new JsonRpcChainSettlementAdapter(
      "bsc",
      rpcUrl,
      Number(process.env.BSC_CHAIN_ID ?? process.env.CHAIN_ID ?? 56),
      Number(process.env.BSC_CONFIRMATION_DEPTH ?? process.env.CONFIRMATION_DEPTH ?? 15),
    );
  }
  if (requested === "ethereum" || requested === "eth") {
    const rpcUrl = process.env.ETHEREUM_RPC_URL;
    if (!rpcUrl) throw new Error("ETHEREUM_RPC_URL is required for Ethereum settlement adapter");
    return new JsonRpcChainSettlementAdapter(
      "ethereum",
      rpcUrl,
      Number(process.env.ETHEREUM_CHAIN_ID ?? 1),
      Number(process.env.ETHEREUM_CONFIRMATION_DEPTH ?? 64),
    );
  }
  if (executionMode === "real") {
    throw new Error(`Unsupported real settlement adapter: ${requested}`);
  }
  throw new Error("No real settlement adapter configured; placeholder settlement fallback has been removed");
}

function hexToNumber(value: string): number {
  return Number.parseInt(value.startsWith("0x") ? value.slice(2) : value, 16);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function transactionRequestFrom(metadata: Record<string, unknown>): TreasuryTransactionRequest {
  const to = String(metadata.to ?? "");
  const data = String(metadata.data ?? "0x");
  if (!/^0x[a-fA-F0-9]{40}$/.test(to)) {
    throw new Error("Real settlement requires router-built settlementTransaction.to");
  }
  if (!/^0x([a-fA-F0-9]{2})*$/.test(data)) {
    throw new Error("Settlement transaction data must be hex bytes");
  }
  return {
    to,
    data,
    valueWei: String(metadata.valueWei ?? "0"),
    gasLimit: optionalString(metadata.gasLimit),
    gasPriceWei: optionalString(metadata.gasPriceWei),
    maxFeePerGasWei: optionalString(metadata.maxFeePerGasWei),
    maxPriorityFeePerGasWei: optionalString(metadata.maxPriorityFeePerGasWei),
  };
}

function transactionRequestsFrom(value: unknown): TreasuryTransactionRequest[] {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value)) {
    throw new Error("preSettlementTransactions must be an array");
  }
  return value.map((item) => transactionRequestFrom(asRecord(item)));
}

function optionalString(value: unknown): string | undefined {
  return value === undefined || value === null || value === "" ? undefined : String(value);
}

function escalatedFee(previousFeeStrategy: Record<string, unknown> | undefined): Partial<TreasuryTransactionRequest> {
  const multiplierBps = BigInt(process.env.STUCK_TX_REPLACEMENT_GAS_MULTIPLIER_BPS ?? "12500");
  const gasPrice = previousFeeStrategy?.gasPrice;
  if (gasPrice !== undefined && gasPrice !== null) {
    return {
      gasPriceWei: ((BigInt(String(gasPrice)) * multiplierBps) / 10_000n).toString(),
    };
  }
  const maxFee = previousFeeStrategy?.maxFeePerGas;
  const maxPriority = previousFeeStrategy?.maxPriorityFeePerGas;
  if (maxFee !== undefined || maxPriority !== undefined) {
    return {
      maxFeePerGasWei: maxFee === undefined || maxFee === null ? undefined : ((BigInt(String(maxFee)) * multiplierBps) / 10_000n).toString(),
      maxPriorityFeePerGasWei:
        maxPriority === undefined || maxPriority === null ? undefined : ((BigInt(String(maxPriority)) * multiplierBps) / 10_000n).toString(),
    };
  }
  return {};
}

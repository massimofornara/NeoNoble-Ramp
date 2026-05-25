import { join } from "node:path";
import { AsyncMutex, atomicWriteJson, readJsonFile } from "../core/persistence.js";
import { logJson, metrics } from "../core/observability.js";
import { isRetryableBroadcastFailure, normalizeFailureReason } from "./smartRetryPolicy.js";

export interface TreasuryTransactionRequest {
  to: string;
  data?: string;
  valueWei?: string;
  gasLimit?: string;
  gasPriceWei?: string;
  maxFeePerGasWei?: string;
  maxPriorityFeePerGasWei?: string;
  nonce?: number;
}

export interface SignedBroadcastResult {
  txHash: string;
  rawTransaction: string;
  nonce: number;
  gasLimit: string;
  feeStrategy: Record<string, string>;
}

type EthersLike = {
  JsonRpcProvider: new (rpcUrl: string, chainId?: number) => {
    getTransactionCount(address: string, blockTag: "pending" | "latest"): Promise<number>;
    estimateGas(request: Record<string, unknown>): Promise<bigint>;
    getFeeData(): Promise<{
      gasPrice?: bigint | null;
      maxFeePerGas?: bigint | null;
      maxPriorityFeePerGas?: bigint | null;
    }>;
    broadcastTransaction(rawTransaction: string): Promise<{ hash: string }>;
  };
  Wallet: new (
    privateKey: string,
    provider: unknown,
  ) => {
    address: string;
    signTransaction(request: Record<string, unknown>): Promise<string>;
  };
};

export class TreasurySigner {
  private readonly nonceManager = new DurableNonceManager(process.env.TREASURY_NONCE_FILE ?? join(process.cwd(), "data", "treasury-nonces.json"));

  constructor(
    private readonly rpcUrl: string,
    private readonly chainId: number,
    private readonly treasuryAddress = process.env.TREASURY_ADDRESS ?? "",
    private readonly privateKey = process.env.TREASURY_PRIVATE_KEY ?? "",
  ) {}

  configured(): boolean {
    return Boolean(this.rpcUrl && this.chainId && this.treasuryAddress && this.privateKey);
  }

  assertConfigured(): void {
    if (!this.rpcUrl) throw new Error("RPC URL is required for real treasury signing");
    if (!this.treasuryAddress) throw new Error("TREASURY_ADDRESS is required for real treasury signing");
    if (!this.privateKey) throw new Error("TREASURY_PRIVATE_KEY is required for real treasury signing");
  }

  async signAndBroadcast(request: TreasuryTransactionRequest): Promise<SignedBroadcastResult> {
    this.assertConfigured();
    const ethers = await loadEthers();
    const provider = new ethers.JsonRpcProvider(this.rpcUrl, this.chainId);
    const wallet = new ethers.Wallet(this.privateKey, provider);
    if (wallet.address.toLowerCase() !== this.treasuryAddress.toLowerCase()) {
      throw new Error("TREASURY_PRIVATE_KEY does not match TREASURY_ADDRESS");
    }

    const maxAttempts = Math.max(1, Number(process.env.BROADCAST_RETRY_ATTEMPTS ?? 3));
    let lastError: unknown;
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      const allocatedNonce = request.nonce === undefined;
      const nonce = request.nonce ?? (await this.nonceManager.allocate(this.treasuryAddress, async () => provider.getTransactionCount(this.treasuryAddress, "pending")));
      const baseRequest: Record<string, unknown> = {
        chainId: this.chainId,
        to: request.to,
        data: request.data ?? "0x",
        value: BigInt(request.valueWei ?? "0"),
        nonce,
      };
      try {
        const gasLimit = request.gasLimit ? BigInt(request.gasLimit) : await provider.estimateGas({ ...baseRequest, from: this.treasuryAddress });
        const feeData = await provider.getFeeData();
        const feeStrategy = feeStrategyFor(request, feeData);
        const tx = {
          ...baseRequest,
          gasLimit,
          ...Object.fromEntries(Object.entries(feeStrategy).map(([key, value]) => [key, BigInt(value)])),
        };

        const rawTransaction = await wallet.signTransaction(tx);
        const broadcast = await provider.broadcastTransaction(rawTransaction);
        if (attempt > 1) {
          metrics.inc("exchange_broadcast_retry_success_total", { reason: normalizeFailureReason(lastError), attempt });
        }
        return {
          txHash: broadcast.hash,
          rawTransaction,
          nonce,
          gasLimit: gasLimit.toString(),
          feeStrategy,
        };
      } catch (error) {
        lastError = error;
        if (allocatedNonce) await this.nonceManager.releaseIfCurrent(this.treasuryAddress, nonce);
        const retryable = request.nonce === undefined && attempt < maxAttempts && isRetryableBroadcastFailure(error);
        metrics.inc("exchange_broadcast_attempt_failures_total", { reason: normalizeFailureReason(error), retryable, attempt });
        logJson("treasury-signer", "broadcast_attempt_failed", {
          reason: normalizeFailureReason(error),
          retryable,
          attempt,
          maxAttempts,
        });
        if (!retryable) throw error;
        if (normalizeFailureReason(error) === "NONCE_MISMATCH") {
          await this.nonceManager.sync(this.treasuryAddress, await provider.getTransactionCount(this.treasuryAddress, "pending"));
        }
        await delay(Number(process.env.BROADCAST_RETRY_DELAY_MS ?? 750) * attempt);
      }
    }
    throw lastError;
  }
}

class DurableNonceManager {
  private readonly mutex = new AsyncMutex();

  constructor(private readonly filePath: string) {}

  async allocate(address: string, chainPendingNonce: () => Promise<number>): Promise<number> {
    return this.mutex.runExclusive(async () => {
      const key = address.toLowerCase();
      const nonces = readJsonFile<Record<string, number>>(this.filePath, {});
      const pending = await chainPendingNonce();
      const next = Math.max(pending, (nonces[key] ?? pending - 1) + 1);
      nonces[key] = next;
      atomicWriteJson(this.filePath, nonces);
      return next;
    });
  }

  async releaseIfCurrent(address: string, nonce: number): Promise<void> {
    await this.mutex.runExclusive(async () => {
      const key = address.toLowerCase();
      const nonces = readJsonFile<Record<string, number>>(this.filePath, {});
      if (nonces[key] === nonce) {
        nonces[key] = nonce - 1;
        atomicWriteJson(this.filePath, nonces);
      }
    });
  }

  async sync(address: string, chainPendingNonce: number): Promise<void> {
    await this.mutex.runExclusive(async () => {
      const key = address.toLowerCase();
      const nonces = readJsonFile<Record<string, number>>(this.filePath, {});
      nonces[key] = Math.max(chainPendingNonce - 1, nonces[key] ?? chainPendingNonce - 1);
      atomicWriteJson(this.filePath, nonces);
    });
  }
}

function feeStrategyFor(
  request: TreasuryTransactionRequest,
  feeData: { gasPrice?: bigint | null; maxFeePerGas?: bigint | null; maxPriorityFeePerGas?: bigint | null },
): Record<string, string> {
  const cap = process.env.MAX_GAS_PRICE ? BigInt(process.env.MAX_GAS_PRICE) : undefined;
  const lowCost = process.env.GAS_STRATEGY === "optimized_low";
  if (request.maxFeePerGasWei || request.maxPriorityFeePerGasWei) {
    const maxFee = BigInt(request.maxFeePerGasWei ?? String(feeData.maxFeePerGas ?? feeData.gasPrice ?? 0n));
    const maxPriority = BigInt(request.maxPriorityFeePerGasWei ?? String(feeData.maxPriorityFeePerGas ?? feeData.gasPrice ?? 0n));
    return {
      maxFeePerGas: capped(maxFee, cap, lowCost).toString(),
      maxPriorityFeePerGas: capped(maxPriority, cap, lowCost).toString(),
    };
  }
  const gasPrice = BigInt(request.gasPriceWei ?? String(feeData.gasPrice ?? feeData.maxFeePerGas ?? 0n));
  return {
    gasPrice: capped(gasPrice, cap, lowCost).toString(),
  };
}

function capped(value: bigint, cap: bigint | undefined, lowCost: boolean): bigint {
  if (value <= 0n) {
    throw new Error("Gas price strategy produced a non-positive fee");
  }
  if (!cap) return value;
  if (value > cap && !lowCost) {
    throw new Error(`Gas price ${value.toString()} exceeds MAX_GAS_PRICE ${cap.toString()}`);
  }
  return value > cap ? cap : value;
}

async function loadEthers(): Promise<EthersLike> {
  try {
    const dynamicImport = new Function("specifier", "return import(specifier)") as (specifier: string) => Promise<EthersLike>;
    return await dynamicImport("ethers");
  } catch (error) {
    throw new Error(
      `ethers dependency is required for treasury signing. Run npm install before real settlement. Cause: ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

import { createHash, randomUUID } from "node:crypto";
import type { CreateOrderInput, EventBus } from "../core/types.js";
import type { IdempotencyStore } from "../core/store.js";
import { WalletService } from "./walletService.js";
import { ComplianceService } from "./complianceService.js";
import { RiskService } from "./riskService.js";

export class OrderService {
  constructor(
    private readonly bus: EventBus,
    private readonly idempotency: IdempotencyStore,
    private readonly walletService: WalletService,
    private readonly complianceService: ComplianceService,
    private readonly riskService: RiskService,
  ) {}

  async createIntent(input: CreateOrderInput): Promise<{ transactionId: string; status: "queued"; duplicate?: boolean }> {
    const existing = this.idempotency.get<{ transactionId: string; status: "queued"; duplicate?: boolean }>(
      "orders.create",
      input.idempotencyKey,
    );
    if (existing) return { ...existing, duplicate: true };

    await this.walletService.assertWalletReady(input.accountId);
    await this.complianceService.assertAllowed(input.accountId);
    this.riskService.assertAllowed({
      userId: input.accountId,
      asset: input.toAsset,
      notional: riskNotional(input),
    });

    const transactionId = randomUUID();
    const traceId = traceIdFor(transactionId, input.metadata?.traceId);
    await this.bus.publish("orders.created", transactionId, {
      traceId,
      userId: input.accountId,
      accountId: input.accountId,
      type: input.type,
      fromAsset: input.fromAsset,
      toAsset: input.toAsset,
      fromAmount: input.fromAmount,
      expectedToAmount: input.expectedToAmount,
      provider: input.provider ?? "real",
      destination: input.destination ?? null,
      metadata: {
        ...(input.metadata ?? {}),
        traceId,
      },
    });

    return this.idempotency.set("orders.create", input.idempotencyKey, {
      transactionId,
      status: "queued",
    });
  }
}

function traceIdFor(transactionId: string, candidate: unknown): string {
  if (typeof candidate === "string" && /^[a-fA-F0-9]{32}$/.test(candidate)) return candidate.toLowerCase();
  return createHash("sha256").update(transactionId).digest("hex").slice(0, 32);
}

function riskNotional(input: CreateOrderInput): string {
  const valuation = input.metadata?.valuation;
  if (valuation && typeof valuation === "object" && "sourceValuationUSDT" in valuation) {
    return String((valuation as Record<string, unknown>).sourceValuationUSDT);
  }
  return input.expectedToAmount;
}

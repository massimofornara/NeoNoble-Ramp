import { createHash, randomUUID } from "node:crypto";
import type { EventBus } from "../core/types.js";
import type { IdempotencyStore } from "../core/store.js";
import { ExecutionPlanner } from "./executionPlanner.js";
import { SolverEngine, type ScheduledIntent } from "./solverEngine.js";

export interface CreateSwapIntentInput {
  idempotencyKey: string;
  accountId: string;
  fromAsset: string;
  toAsset: "USDT" | "USDC" | "WBNB" | string;
  amount: string;
  expectedToAmount: string;
  provider?: string;
  metadata?: Record<string, unknown>;
}

export interface CreateOfframpIntentInput {
  idempotencyKey: string;
  accountId: string;
  fromAsset: string;
  fiatCurrency: "EUR" | string;
  amount: string;
  expectedFiatAmount: string;
  provider?: string;
  metadata?: Record<string, unknown>;
}

export class IntentService {
  constructor(
    private readonly bus: EventBus,
    private readonly idempotency: IdempotencyStore,
    private readonly planner: ExecutionPlanner,
    private readonly solver: SolverEngine,
  ) {}

  async createSwapIntent(input: CreateSwapIntentInput): Promise<ScheduledIntent & { duplicate?: boolean }> {
    const existing = this.idempotency.get<ScheduledIntent & { duplicate?: boolean }>("intent.swap.create", input.idempotencyKey);
    if (existing) return { ...existing, duplicate: true };

    const intentId = randomUUID();
    const traceId = traceIdFor(intentId, input.metadata?.traceId);
    const executionPlan = await this.planner.planSwap({
      intentId,
      accountId: input.accountId,
      fromAsset: input.fromAsset,
      toAsset: input.toAsset,
      amount: input.amount,
      expectedToAmount: input.expectedToAmount,
    });
    const intent = await this.bus.publish("execution.intent_created", intentId, {
      intentId,
      traceId,
      userId: input.accountId,
      accountId: input.accountId,
      type: "swap",
      fromAsset: input.fromAsset,
      toAsset: input.toAsset,
      fromAmount: input.amount,
      expectedToAmount: input.expectedToAmount,
      provider: input.provider ?? "real",
      executionMode: "intent-based",
      metadata: {
        ...(input.metadata ?? {}),
        traceId,
      },
    });
    const scheduled = await this.solver.scheduleIntent(intent, executionPlan);
    return this.idempotency.set("intent.swap.create", input.idempotencyKey, scheduled);
  }

  async createOfframpIntent(input: CreateOfframpIntentInput): Promise<ScheduledIntent & { duplicate?: boolean; fiatRoute?: string }> {
    const existing = this.idempotency.get<ScheduledIntent & { duplicate?: boolean; fiatRoute?: string }>(
      "intent.offramp.create",
      input.idempotencyKey,
    );
    if (existing) return { ...existing, duplicate: true };

    const intentId = randomUUID();
    const traceId = traceIdFor(intentId, input.metadata?.traceId);
    const executionPlan = this.planner.planOfframp({
      fromAsset: input.fromAsset,
      fiatCurrency: input.fiatCurrency,
      amount: input.amount,
    });
    const intent = await this.bus.publish("execution.intent_created", intentId, {
      intentId,
      traceId,
      userId: input.accountId,
      accountId: input.accountId,
      type: "offramp",
      fromAsset: input.fromAsset,
      toAsset: input.fiatCurrency,
      fromAmount: input.amount,
      expectedToAmount: input.expectedFiatAmount,
      provider: input.provider ?? "real",
      executionMode: "intent-based",
      destination: "EUR-SEPA",
      metadata: {
        ...(input.metadata ?? {}),
        traceId,
      },
    });
    const scheduled = await this.solver.scheduleIntent(intent, executionPlan);
    return this.idempotency.set("intent.offramp.create", input.idempotencyKey, {
      ...scheduled,
      fiatRoute: executionPlan.fiatRoute,
    });
  }
}

function traceIdFor(intentId: string, candidate: unknown): string {
  if (typeof candidate === "string" && /^[a-fA-F0-9]{32}$/.test(candidate)) return candidate.toLowerCase();
  return createHash("sha256").update(intentId).digest("hex").slice(0, 32);
}

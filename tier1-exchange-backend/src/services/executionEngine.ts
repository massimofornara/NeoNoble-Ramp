import type { DomainEvent, EventBus, ExecutionRequestInput } from "../core/types.js";
import type { IdempotencyStore } from "../core/store.js";
import { Interface, parseUnits } from "ethers";
import { metrics } from "../core/observability.js";
import { ValuationService, type ValuationMetadata } from "./valuationService.js";
import { SwapRouterService, type SwapExecutionPlan, type SwapQuote } from "./swapRouterService.js";
import { OfframpRouterService } from "./offrampRouterService.js";
import { TreasuryOnChainService } from "./treasuryOnChainService.js";
import { productionAssetRegistry } from "./assetRegistry.js";
import { normalizeFailureReason } from "./smartRetryPolicy.js";

export class ExecutionEngine {
  private readonly valuationService = new ValuationService();

  constructor(
    private readonly bus: EventBus,
    private readonly idempotency: IdempotencyStore,
  ) {}

  registerConsumers(): void {
    this.bus.subscribe("orders.created", "execution-engine.order-created", async (event) => {
      await this.requestExecution({
        idempotencyKey: `event:${event.eventId}`,
        transactionId: event.transactionId,
        accountId: String(event.payload.accountId),
        type: event.payload.type as "swap" | "offramp",
        fromAsset: String(event.payload.fromAsset),
        toAsset: String(event.payload.toAsset),
        fromAmount: String(event.payload.fromAmount),
        expectedToAmount: String(event.payload.expectedToAmount),
        provider: String(event.payload.provider ?? "real"),
        metadata: asRecord(event.payload.metadata),
      });
    });

    this.bus.subscribe("execution.scheduled", "execution-engine.intent-scheduled", async (event) => {
      await this.requestExecution({
        idempotencyKey: `event:${event.eventId}`,
        transactionId: event.transactionId,
        accountId: String(event.payload.accountId),
        type: event.payload.type as "swap" | "offramp",
        fromAsset: String(event.payload.fromAsset),
        toAsset: String(event.payload.toAsset),
        fromAmount: String(event.payload.fromAmount),
        expectedToAmount: String(event.payload.expectedToAmount),
        provider: String(event.payload.provider ?? "real"),
        metadata: {
          ...asRecord(event.payload.metadata),
          intentId: event.payload.intentId,
          intentExecutionPlan: event.payload.executionPlan,
          solver: event.payload.solver,
          executionMode: "intent-based",
        },
      });
    });

    this.bus.subscribe("execution.requested", "execution-engine.worker", async (event) => {
      await this.completeExecution(event);
    });
  }

  async requestExecution(input: ExecutionRequestInput): Promise<{ transactionId: string; status: "queued"; duplicate?: boolean }> {
    const existing = this.idempotency.get<{ transactionId: string; status: "queued"; duplicate?: boolean }>(
      "execution.request",
      input.idempotencyKey,
    );
    if (existing) return { ...existing, duplicate: true };

    await this.bus.publish("execution.requested", input.transactionId, {
      accountId: input.accountId,
      type: input.type,
      fromAsset: input.fromAsset,
      toAsset: input.toAsset,
      fromAmount: input.fromAmount,
      expectedToAmount: input.expectedToAmount,
      provider: input.provider ?? "real",
      metadata: input.metadata ?? {},
      valuation: this.valuationFor(input),
    });

    return this.idempotency.set("execution.request", input.idempotencyKey, {
      transactionId: input.transactionId,
      status: "queued",
    });
  }

  private async completeExecution(event: DomainEvent): Promise<void> {
    const existing = this.idempotency.get<{ transactionId: string; status: "completed" | "failed" }>(
      "execution.pipeline",
      event.eventId,
    );
    if (existing) return;
    try {
      await this.bus.publish("execution.started", event.transactionId, {
        traceId: event.payload.traceId ?? asRecord(event.payload.metadata).traceId,
        accountId: event.payload.accountId,
        type: event.payload.type,
        provider: event.payload.provider,
        fromAsset: event.payload.fromAsset,
        toAsset: event.payload.toAsset,
        fromAmount: event.payload.fromAmount,
        expectedToAmount: event.payload.expectedToAmount,
        metadata: event.payload.metadata ?? {},
        workerGroup: "execution-engine.worker",
      });
      metrics.observe("exchange_execution_latency_ms", Date.now() - Date.parse(event.timestamp), { type: String(event.payload.type) });
      await this.assertTreasurySourceAvailable(event);
      const valuation = asRecord(event.payload.valuation);
      const metadata = await this.executionMetadata(event, valuation);
      const executedAmount = typeof valuation.targetAmount === "string" ? valuation.targetAmount : String(event.payload.expectedToAmount);
      await this.bus.publish("execution.completed", event.transactionId, {
        traceId: event.payload.traceId ?? asRecord(event.payload.metadata).traceId,
        accountId: event.payload.accountId,
        type: event.payload.type,
        provider: event.payload.provider,
        fromAsset: event.payload.fromAsset,
        toAsset: event.payload.toAsset,
        fromAmount: event.payload.fromAmount,
        executedAmount,
        executionReference: `exec_${event.eventId}`,
        valuation,
        metadata,
        routing: {
          mode: "stateless-worker",
          partition: event.partition,
          workerGroup: "execution-engine.worker",
          supportsPartialFills: true,
        },
      });
      await this.idempotency.set("execution.pipeline", event.eventId, {
        transactionId: event.transactionId,
        status: "completed",
      });
    } catch (error) {
      await this.publishExecutionFailed(event, error);
      await this.idempotency.set("execution.pipeline", event.eventId, {
        transactionId: event.transactionId,
        status: "failed",
      });
    }
  }

  private async executionMetadata(event: DomainEvent, valuation: Record<string, unknown>): Promise<Record<string, unknown>> {
    const metadata = asRecord(event.payload.metadata);
    const provider = String(event.payload.provider ?? "");
    if (provider !== "real") return metadata;
    if (event.payload.type === "swap") {
      const router = new SwapRouterService();
      const intentPlan = asRecord(metadata.intentExecutionPlan);
      const inventoryBacked = await this.inventoryBackedSwapMetadata(event, valuation);
      if (inventoryBacked) {
        return {
          ...metadata,
          ...inventoryBacked,
        };
      }
      const venueBundle = venueSettlementBundle(intentPlan, event);
      if (venueBundle) {
        return {
          ...metadata,
          preSettlementTransactions: venueBundle.preSettlementTransactions,
          settlementTransaction: venueBundle.settlementTransaction,
          executionPlan: {
            ...intentPlan,
            settlementMode: "executable-rfq-or-sor-calldata",
          },
          routingDecision: {
            selectedRoute: venueBundle.route,
            source: venueBundle.source,
            executableQuote: venueBundle.quote,
          },
        };
      }
      if (Array.isArray(intentPlan.slices)) {
        return this.intentSwapMetadata(router, event, metadata, intentPlan);
      }
      const decision = await this.buildExecutableSwapPlan(router, event, valuation);
      return {
        ...metadata,
        preSettlementTransactions: decision.plan.preSettlementTransactions,
        settlementTransaction: decision.plan.transaction,
        executionPlan: decision.plan,
        routingDecision: {
          selectedRoute: {
            routeId: decision.plan.routeId,
            liquiditySource: decision.plan.liquiditySource,
            router: decision.plan.router,
            path: decision.plan.path,
          },
          quote: decision.quote,
          attempts: decision.attempts,
        },
      };
    }
    if (event.payload.type === "offramp") {
      const valuationMetadata = valuation as unknown as ValuationMetadata;
      const offrampRouter = new OfframpRouterService();
      const intentPlan = asRecord(metadata.intentExecutionPlan);
      if (Array.isArray(intentPlan.slices)) {
        return this.intentOfframpMetadata(offrampRouter, event, metadata, intentPlan);
      }
      const plan = offrampRouter.buildOfframp({
        fromAsset: String(event.payload.fromAsset),
        amount: String(event.payload.fromAmount),
        fiatCurrency: String(event.payload.toAsset),
        valuation: valuationMetadata,
        custodyAddress: typeof metadata.custodyAddress === "string" ? metadata.custodyAddress : undefined,
      });
      await offrampRouter.assertExecutablePreflight(plan);
      return {
        ...metadata,
        settlementTransaction: plan.transaction,
        executionPlan: plan,
        preflight: {
          gasSimulation: "passed",
          custodyAddress: plan.custodyAddress,
          tokenAddress: plan.tokenAddress,
        },
      };
    }
    return metadata;
  }

  private async intentSwapMetadata(
    router: SwapRouterService,
    event: DomainEvent,
    metadata: Record<string, unknown>,
    intentPlan: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const slices = arrayOfRecords(intentPlan.slices);
    const preSettlementTransactions: unknown[] = [];
    const settlementTransactions: unknown[] = [];
    const sliceExecutions: Array<Record<string, unknown>> = [];
    const attempts: Array<Record<string, unknown>> = [];
    for (const slice of slices) {
      const amount = String(slice.amount ?? "");
      const sliceValuation = await this.valuationService.swapNenoToAsset(amount, String(event.payload.toAsset));
      const sliceEvent: DomainEvent = {
        ...event,
        payload: {
          ...event.payload,
          fromAmount: amount,
          valuation: sliceValuation as unknown as Record<string, unknown>,
          metadata: {
            ...metadata,
            slippageBps: slice.slippageBps,
          },
        },
      };
      const decision = await this.buildExecutableSwapPlan(router, sliceEvent, sliceValuation as unknown as Record<string, unknown>);
      preSettlementTransactions.push(...decision.plan.preSettlementTransactions);
      settlementTransactions.push(decision.plan.transaction);
      attempts.push(...decision.attempts.map((attempt) => ({ ...attempt, sliceId: slice.sliceId })));
      sliceExecutions.push({
        ...slice,
        valuation: sliceValuation,
        route: decision.plan.path,
        routeId: decision.plan.routeId,
        liquiditySource: decision.plan.liquiditySource,
        quote: decision.quote,
      });
    }
    const finalTransaction = settlementTransactions.at(-1);
    if (!finalTransaction) {
      throw new Error("Intent execution plan did not produce settlement transactions");
    }
    return {
      ...metadata,
      preSettlementTransactions: [...preSettlementTransactions, ...settlementTransactions.slice(0, -1)],
      settlementTransaction: finalTransaction,
      executionPlan: {
        ...intentPlan,
        settlementMode: "batch-twap",
        slices: sliceExecutions,
      },
      routingDecision: {
        selectedRoute: intentPlan.route,
        quote: sliceExecutions.at(-1)?.quote,
        attempts,
        batchSize: sliceExecutions.length,
      },
    };
  }

  private async intentOfframpMetadata(
    offrampRouter: OfframpRouterService,
    event: DomainEvent,
    metadata: Record<string, unknown>,
    intentPlan: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const slices = arrayOfRecords(intentPlan.slices);
    const transactions: unknown[] = [];
    const sliceExecutions: Array<Record<string, unknown>> = [];
    for (const slice of slices) {
      const amount = String(slice.amount ?? "");
      const sliceValuation = this.valuationService.offrampNenoToFiatEquivalent(
        amount,
        String(metadata.rate ?? "20000"),
        String(event.payload.toAsset),
      );
      const plan = offrampRouter.buildOfframp({
        fromAsset: String(event.payload.fromAsset),
        amount,
        fiatCurrency: String(event.payload.toAsset),
        valuation: sliceValuation,
        custodyAddress: typeof metadata.custodyAddress === "string" ? metadata.custodyAddress : undefined,
      });
      await offrampRouter.assertExecutablePreflight(plan);
      transactions.push(plan.transaction);
      sliceExecutions.push({
        ...slice,
        valuation: sliceValuation,
        custodyAddress: plan.custodyAddress,
        tokenAddress: plan.tokenAddress,
      });
    }
    const finalTransaction = transactions.at(-1);
    if (!finalTransaction) {
      throw new Error("Offramp intent execution plan did not produce settlement transactions");
    }
    return {
      ...metadata,
      preSettlementTransactions: transactions.slice(0, -1),
      settlementTransaction: finalTransaction,
      executionPlan: {
        ...intentPlan,
        settlementMode: "offramp-ladder",
        slices: sliceExecutions,
      },
      preflight: {
        gasSimulation: "passed",
        slices: sliceExecutions.length,
      },
    };
  }

  private async buildExecutableSwapPlan(
    router: SwapRouterService,
    event: DomainEvent,
    valuation: Record<string, unknown>,
  ): Promise<{ plan: SwapExecutionPlan; quote: SwapQuote; attempts: Array<Record<string, unknown>> }> {
    const metadata = asRecord(event.payload.metadata);
    const requestedSlippage = numberFrom(metadata.slippageBps, Number(process.env.SWAP_SLIPPAGE_BPS ?? 50)) ?? 50;
    const adaptiveSlippage = Math.min(5000, Math.ceil(requestedSlippage * 1.5));
    const routes = router.routeCandidates(String(event.payload.fromAsset), String(event.payload.toAsset));
    const stages = [
      { name: "base-slippage", slippageBps: requestedSlippage, routes: routes.slice(0, 1) },
      { name: "adaptive-slippage", slippageBps: adaptiveSlippage, routes: routes.slice(0, 1) },
      { name: "route-change", slippageBps: adaptiveSlippage, routes: routes.slice(1) },
    ];
    const attempts: Array<Record<string, unknown>> = [];
    for (const stage of stages) {
      if (stage.routes.length === 0) {
        attempts.push({
          stage: stage.name,
          status: "skipped",
          reason: "no alternate liquidity source configured",
        });
        continue;
      }
      const valid: Array<{ plan: SwapExecutionPlan; quote: SwapQuote }> = [];
      for (const route of stage.routes) {
        const plan = router.buildSwap({
          fromAsset: String(event.payload.fromAsset),
          toAsset: String(event.payload.toAsset),
          amount: String(event.payload.fromAmount),
          valuation: valuation as unknown as ValuationMetadata,
          recipient: typeof metadata.recipient === "string" ? metadata.recipient : undefined,
          slippageBps: stage.slippageBps,
          deadlineSeconds: numberFrom(metadata.deadlineSeconds, undefined),
          route,
        });
        try {
          const quote = await router.assertExecutableQuote(plan);
          attempts.push({
            stage: stage.name,
            routeId: route.routeId,
            liquiditySource: route.liquiditySource,
            slippageBps: stage.slippageBps,
            status: "valid",
            quote,
          });
          valid.push({ plan, quote });
        } catch (error) {
          attempts.push({
            stage: stage.name,
            routeId: route.routeId,
            liquiditySource: route.liquiditySource,
            slippageBps: stage.slippageBps,
            status: "rejected",
            error: error instanceof Error ? error.message : String(error),
          });
        }
      }
      const best = valid.sort((left, right) => compareBigIntStrings(right.quote.quotedOutRaw, left.quote.quotedOutRaw))[0];
      if (best) {
        return { ...best, attempts };
      }
    }
    throw new Error(`REJECTED_INSUFFICIENT_LIQUIDITY: ${JSON.stringify(attempts)}`);
  }

  private async inventoryBackedSwapMetadata(event: DomainEvent, valuation: Record<string, unknown>): Promise<Record<string, unknown> | undefined> {
    if (process.env.ENABLE_TREASURY_INVENTORY_SWAPS === "0") return undefined;
    const recipient = process.env.SWAP_RECIPIENT_ADDRESS;
    const treasuryAddress = process.env.TREASURY_ADDRESS;
    if (!recipient || !/^0x[a-fA-F0-9]{40}$/.test(recipient) || recipient.toLowerCase() === String(treasuryAddress).toLowerCase()) return undefined;
    const toAsset = String(event.payload.toAsset).toUpperCase();
    const asset = productionAssetRegistry().optional(toAsset);
    if (!asset || asset.native || asset.chainName !== "bsc" || !asset.checksumAddress) return undefined;
    const expectedAmount = String(valuation.targetAmount ?? event.payload.expectedToAmount ?? "0");
    const treasuryBalances = await new TreasuryOnChainService().balances();
    const balances = Array.isArray(treasuryBalances.balances) ? (treasuryBalances.balances as Array<Record<string, unknown>>) : [];
    const row = balances.find((item) => String(item.asset).toUpperCase() === toAsset);
    if (!row || Number(row.balance ?? 0) < Number(expectedAmount)) return undefined;
    const transfer = new Interface(["function transfer(address to,uint256 amount) returns (bool)"]);
    const amountRaw = parseUnits(expectedAmount, asset.decimals).toString();
    return {
      settlementTransaction: {
        to: asset.checksumAddress,
        data: transfer.encodeFunctionData("transfer", [recipient, amountRaw]),
        valueWei: "0",
      },
      executionPlan: {
        settlementMode: "treasury-inventory-backed-swap",
        outputAsset: toAsset,
        recipient,
        inventoryBalanceBefore: String(row.balance),
      },
      routingDecision: {
        selectedRoute: [String(event.payload.fromAsset), toAsset],
        source: "treasury-inventory",
        reason: "output inventory sufficient; avoids external AMM slippage",
      },
    };
  }

  private async publishExecutionFailed(event: DomainEvent, error: unknown): Promise<void> {
    const message = error instanceof Error ? error.message : String(error);
    await this.bus.publish("execution.failed", event.transactionId, {
      traceId: event.payload.traceId ?? asRecord(event.payload.metadata).traceId,
      accountId: event.payload.accountId,
      type: event.payload.type,
      provider: event.payload.provider,
      fromAsset: event.payload.fromAsset,
      toAsset: event.payload.toAsset,
      fromAmount: event.payload.fromAmount,
      expectedToAmount: event.payload.expectedToAmount,
      reason: executionFailureReason(message),
      error: message,
      metadata: asRecord(event.payload.metadata),
      fallbackPolicy: ["rfq-retry", "sor-reroute", "twap-split", "internal-crossing", "amm-last-resort"],
    });
    metrics.inc("exchange_execution_failures_total", { reason: executionFailureReason(message), type: String(event.payload.type) });
  }

  private valuationFor(input: ExecutionRequestInput): Record<string, unknown> {
    const metadataValuation = input.metadata?.valuation;
    if (metadataValuation && typeof metadataValuation === "object" && !Array.isArray(metadataValuation)) {
      return metadataValuation as Record<string, unknown>;
    }
    if (input.type === "swap" && input.fromAsset === "NENO" && input.toAsset === "WBNB") {
      return this.valuationService.swapNenoToWbnb(input.fromAmount) as unknown as Record<string, unknown>;
    }
    if (input.type === "offramp" && input.fromAsset === "NENO") {
      const metadata = input.metadata ?? {};
      const rate = typeof metadata.rate === "string" ? metadata.rate : process.env.NENO_USDT_RATE ?? "20000";
      return this.valuationService.offrampNenoToFiatEquivalent(input.fromAmount, rate, input.toAsset) as unknown as Record<string, unknown>;
    }
    return {
      sourceAsset: input.fromAsset,
      sourceAmount: input.fromAmount,
      sourceValuationUSDT: input.expectedToAmount,
      exchangeRate: "deterministic passthrough",
      targetAsset: input.toAsset,
      targetAmount: input.expectedToAmount,
    };
  }

  private async assertTreasurySourceAvailable(event: DomainEvent): Promise<void> {
    if (String(event.payload.provider ?? "") !== "real") return;
    if (process.env.TREASURY_BALANCE_GUARD === "0") return;
    const asset = String(event.payload.fromAsset ?? "").toUpperCase();
    const required = Number(event.payload.fromAmount ?? 0);
    if (!asset || !Number.isFinite(required) || required <= 0) return;
    const treasury = await new TreasuryOnChainService().balances();
    const balances = Array.isArray(treasury.balances) ? (treasury.balances as Array<Record<string, unknown>>) : [];
    const row = balances.find((item) => String(item.asset).toUpperCase() === asset);
    if (!row) return;
    const available = Number(row.balance ?? 0);
    if (available >= required) return;
    throw new Error(
      `TREASURY_SOURCE_ASSET_INSUFFICIENT: asset=${asset} balance=${String(row.balance ?? "0")} required=${String(event.payload.fromAmount)}; routing fallbacks exhausted before broadcast`,
    );
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function arrayOfRecords(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item)) : [];
}

function numberFrom(value: unknown, fallback: number | undefined): number | undefined {
  if (value === undefined || value === null || value === "") return fallback;
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function compareBigIntStrings(left: string, right: string): number {
  const leftValue = BigInt(left);
  const rightValue = BigInt(right);
  return leftValue > rightValue ? 1 : leftValue < rightValue ? -1 : 0;
}

function executionFailureReason(message: string): string {
  if (message.startsWith("TREASURY_SOURCE_ASSET_INSUFFICIENT")) return "TREASURY_SOURCE_ASSET_INSUFFICIENT";
  if (message.startsWith("RFQ_REQUIRED_NO_MAKER_QUOTE")) return "RFQ_REQUIRED_NO_MAKER_QUOTE";
  if (message.startsWith("REJECTED_INSUFFICIENT_LIQUIDITY")) return "REJECTED_INSUFFICIENT_LIQUIDITY";
  if (message.startsWith("OFFRAMP_PREFLIGHT_FAILED")) return "OFFRAMP_PREFLIGHT_FAILED";
  return normalizeFailureReason(message);
}

interface VenueSettlementBundle {
  source: string;
  route: unknown;
  quote: Record<string, unknown>;
  preSettlementTransactions: Record<string, unknown>[];
  settlementTransaction: Record<string, unknown>;
}

function venueSettlementBundle(intentPlan: Record<string, unknown>, event: DomainEvent): VenueSettlementBundle | undefined {
  for (const quote of executableQuoteCandidates(intentPlan)) {
    if (quoteExpired(quote)) continue;
    const raw = quoteRaw(quote);
    const settlementTransaction = transactionFromRaw(raw);
    if (!settlementTransaction) continue;
    const source = String(quote.liquiditySource ?? quote.venue ?? "executable-venue");
    return {
      source,
      route: quote.route,
      quote: {
        quoteId: quote.quoteId,
        venue: quote.venue,
        liquiditySource: quote.liquiditySource,
        outputAmount: quote.outputAmount,
        expiresAt: quote.expiresAt,
        makerFillGuarantee: asRecord(quote.metadata).makerFillGuarantee,
        signedExecutableQuote: asRecord(quote.metadata).signedExecutableQuote,
      },
      preSettlementTransactions: [
        ...preSettlementTransactionsFromRaw(raw),
        ...approvalTransactionsFromRaw(raw, event, settlementTransaction),
      ],
      settlementTransaction,
    };
  }
  return undefined;
}

function executableQuoteCandidates(intentPlan: Record<string, unknown>): Record<string, unknown>[] {
  const institutional = asRecord(intentPlan.institutionalRfq);
  const rfq = asRecord(intentPlan.rfq);
  const sor = asRecord(intentPlan.sor);
  return [
    asRecord(institutional.selectedExecutable),
    asRecord(institutional.selected),
    ...arrayOfRecords(institutional.quotes),
    asRecord(asRecord(rfq.selected).quote),
    ...arrayOfRecords(rfq.quotes),
    asRecord(asRecord(sor.selected).quote),
    ...arrayOfRecords(sor.ranked).map((ranked) => asRecord(ranked.quote)),
  ].filter((quote) => Boolean(quote.quoteId || quote.liquiditySource || quote.metadata));
}

function quoteExpired(quote: Record<string, unknown>): boolean {
  const expiresAt = String(quote.expiresAt ?? "");
  if (!expiresAt) return false;
  const minTtlMs = Number(process.env.EXECUTABLE_QUOTE_MIN_TTL_MS ?? 5_000);
  return Date.parse(expiresAt) <= Date.now() + minTtlMs;
}

function quoteRaw(quote: Record<string, unknown>): Record<string, unknown> {
  const metadata = asRecord(quote.metadata);
  return asRecord(metadata.raw ?? quote.raw ?? metadata);
}

function transactionFromRaw(raw: Record<string, unknown>): Record<string, unknown> | undefined {
  const tx = firstRecord(raw.transaction, raw.tx, raw.settlementTransaction, asRecord(raw.execution).transaction, asRecord(raw.execution).tx);
  if (!tx) return undefined;
  const to = String(tx.to ?? tx.target ?? "");
  const data = String(tx.data ?? tx.calldata ?? "");
  if (!/^0x[a-fA-F0-9]{40}$/.test(to) || !/^0x([a-fA-F0-9]{2})*$/.test(data)) return undefined;
  return {
    to,
    data,
    valueWei: String(tx.valueWei ?? tx.value ?? "0"),
    gasLimit: tx.gasLimit ? String(tx.gasLimit) : undefined,
    gasPriceWei: tx.gasPriceWei ? String(tx.gasPriceWei) : undefined,
  };
}

function preSettlementTransactionsFromRaw(raw: Record<string, unknown>): Record<string, unknown>[] {
  return [
    ...arrayOfRecords(raw.preSettlementTransactions),
    ...arrayOfRecords(raw.approvalTransactions),
    ...arrayOfRecords(raw.approvals),
    asRecord(raw.approvalTransaction),
    asRecord(raw.approval),
  ]
    .map((item) => transactionFromRaw({ transaction: item }))
    .filter((item): item is Record<string, unknown> => Boolean(item));
}

function approvalTransactionsFromRaw(raw: Record<string, unknown>, event: DomainEvent, settlementTransaction: Record<string, unknown>): Record<string, unknown>[] {
  if (preSettlementTransactionsFromRaw(raw).length > 0) return [];
  const allowanceTarget = String(raw.allowanceTarget ?? raw.approvalTarget ?? raw.spender ?? asRecord(raw.transaction).allowanceTarget ?? "");
  if (!/^0x[a-fA-F0-9]{40}$/.test(allowanceTarget)) return [];
  if (allowanceTarget.toLowerCase() === String(settlementTransaction.to).toLowerCase() && raw.skipApproval === true) return [];
  const fromAsset = String(event.payload.fromAsset);
  const amount = String(event.payload.fromAmount);
  const token = productionAssetRegistry().address(fromAsset);
  const amountRaw = parseUnits(amount, productionAssetRegistry().decimals(fromAsset)).toString();
  const approve = new Interface(["function approve(address spender,uint256 amount) returns (bool)"]);
  return [
    {
      to: token,
      data: approve.encodeFunctionData("approve", [allowanceTarget, amountRaw]),
      valueWei: "0",
    },
  ];
}

function firstRecord(...values: unknown[]): Record<string, unknown> | undefined {
  return values.find((value): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value));
}

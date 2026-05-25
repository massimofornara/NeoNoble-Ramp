import "../core/env.js";
import { createServer } from "node:http";
import type { IncomingMessage, ServerResponse } from "node:http";
import { createTier1ExchangeApp } from "../app.js";
import { metrics } from "../core/observability.js";
import { readJson, readRawBody, requireIdempotencyKey, sendJson } from "./http.js";
import { ValuationService } from "../services/valuationService.js";
import { TreasuryOnChainService } from "../services/treasuryOnChainService.js";
import { TreasuryFundingBootstrapService } from "../services/treasuryFundingBootstrapService.js";
import { ExecutionReadinessController } from "../services/executionReadinessController.js";

type App = ReturnType<typeof createTier1ExchangeApp>;
type FlowScope = "all" | "swap" | "offramp";

export function createApiServer(options: { dataDir?: string } = {}) {
  const app = createTier1ExchangeApp(options);
  const server = createServer(async (request, response) => {
    try {
      await route(request, response, app);
    } catch (error) {
      sendJson(response, 400, {
        error: error instanceof Error ? error.message : String(error),
      });
    }
  });
  return { app, server };
}

async function route(request: IncomingMessage, response: ServerResponse, app: App) {
  const method = request.method ?? "GET";
  const url = new URL(request.url ?? "/", "http://localhost");
  app.securityService.assertRateLimit(`${request.socket.remoteAddress ?? "local"}:${url.pathname}`);

  if (method === "GET" && url.pathname === "/metrics") {
    response.writeHead(200, { "content-type": "text/plain; version=0.0.4" });
    response.end(metrics.toPrometheus());
    return;
  }

  if (method === "GET" && url.pathname === "/health") {
    sendJson(response, 200, {
      status: "ok",
      eventBus: "kafka-compatible-postgres-primary",
      replayable: true,
      sourceOfTruth: process.env.PERSISTENCE_DRIVER === "postgres" ? "postgres" : "append-only-event-stream",
      cluster: app.store.events.clusterStatus(),
      persistence: await safePostgresStatus(app),
      settlementAdapters: {
        bsc: process.env.BSC_RPC_URL ? "configured" : "configure BSC_RPC_URL",
        ethereum: process.env.ETHEREUM_RPC_URL ? "configured" : "configure ETHEREUM_RPC_URL",
      },
      assetRegistry: app.assetRegistry.report(),
      fireblocks: app.fireblocksService.readiness(),
      observability: {
        metrics: "/metrics",
        structuredLogs: true,
      },
    });
    return;
  }

  if (method === "GET" && url.pathname === "/production/preflight") {
    sendJson(response, 200, await productionPreflightReport(app, flowScope(url)));
    return;
  }

  if (method === "GET" && url.pathname === "/treasury/inventory") {
    sendJson(response, 200, app.treasuryEngine.report(undefined, await new TreasuryOnChainService(app.assetRegistry).balances()));
    return;
  }

  if (method === "GET" && url.pathname === "/treasury/status") {
    const onChain = await new TreasuryOnChainService(app.assetRegistry).balances();
    sendJson(response, 200, {
      ...app.treasuryEngine.status(onChain),
      onChain,
    });
    return;
  }

  if (method === "GET" && url.pathname === "/treasury/exposure") {
    const onChain = await new TreasuryOnChainService(app.assetRegistry).balances();
    sendJson(response, 200, {
      ...app.treasuryEngine.exposure(onChain),
      onChain,
    });
    return;
  }

  if (method === "GET" && url.pathname === "/treasury/rebalance-report") {
    const onChain = await new TreasuryOnChainService(app.assetRegistry).balances();
    sendJson(response, 200, app.treasuryEngine.rebalanceReport(onChain));
    return;
  }

  if (method === "GET" && url.pathname === "/treasury/bootstrap-plan") {
    sendJson(response, 200, await new TreasuryFundingBootstrapService(app.assetRegistry).plan());
    return;
  }

  if (method === "GET" && url.pathname === "/execution/readiness") {
    sendJson(response, 200, await new ExecutionReadinessController(app.assetRegistry).evaluate({ largeIntent: url.searchParams.get("largeIntent") === "1" }));
    return;
  }

  if (method === "GET" && url.pathname === "/fireblocks/readiness") {
    sendJson(response, 200, app.fireblocksService.readiness());
    return;
  }

  if (method === "GET" && url.pathname === "/fireblocks/vault") {
    await app.store.ready();
    sendJson(response, 200, await app.fireblocksService.vaultStatus());
    return;
  }

  if (method === "GET" && url.pathname === "/assets/registry") {
    sendJson(response, 200, app.assetRegistry.report());
    return;
  }

  if (method === "GET" && url.pathname === "/exchange-os/status") {
    sendJson(response, 200, app.executionControlPlane.status());
    return;
  }

  if (method === "GET" && url.pathname === "/custody/policy") {
    const amountUsd = url.searchParams.get("amountUsd") ?? "0";
    sendJson(response, 200, app.mpcWalletSigner.signingEnvelope(amountUsd));
    return;
  }

  if (method === "POST" && (url.pathname === "/swap" || url.pathname === "/production/execute-real-swap")) {
    const body = await readJson<Record<string, unknown>>(request);
    const idempotencyKey = requireIdempotencyKey(request.headers, body);
    assertRealExecution(body);
    await assertProductionReady(app, "swap");

    const amount = stringValue(body.amount ?? body.fromAmount ?? "100");
    const fromToken = stringValue(body.fromToken ?? "NENO");
    const toToken = stringValue(body.toToken ?? "WBNB");
    const userId = stringValue(body.userId ?? "massi-prod-001");
    const valuation = await new ValuationService().swapNenoToAsset(amount, toToken);

    const result = await app.intentService.createSwapIntent({
      idempotencyKey,
      accountId: userId,
      fromAsset: fromToken,
      toAsset: toToken,
      amount,
      expectedToAmount: valuation.targetAmount,
      provider: "real",
      metadata: {
        valuation,
        recipient: typeof body.recipient === "string" ? body.recipient : undefined,
        slippageBps: body.slippageBps,
        deadlineSeconds: body.deadlineSeconds,
      },
    });

    sendJson(response, 202, {
      intentId: result.intentId,
      orderId: result.intentId,
      transactionId: result.intentId,
      traceId: result.traceId,
      executionMode: "intent-based",
      amount: valuation.targetAmount,
      exchangeRate: valuation.exchangeRate,
      status: result.status,
      route: result.route,
      twap: result.twap,
      statusUrl: `/orders/${result.intentId}`,
    });
    return;
  }

  if (method === "POST" && url.pathname === "/offramp") {
    const body = await readJson<Record<string, unknown>>(request);
    const idempotencyKey = requireIdempotencyKey(request.headers, body);
    assertRealExecution(body);
    await assertProductionReady(app, "offramp");

    const amount = stringValue(body.amount ?? body.fromAmount);
    const rate = stringValue(body.rate ?? "20000");
    const fiatCurrency = stringValue(body.fiatCurrency ?? "EUR");
    const fromToken = stringValue(body.fromToken ?? "NENO");
    const userId = stringValue(body.userId);
    assertPositiveDecimal(amount, "amount");
    assertPositiveDecimal(rate, "rate");

    const valuation = new ValuationService().offrampNenoToFiatEquivalent(amount, rate, fiatCurrency);
    const result = await app.intentService.createOfframpIntent({
      idempotencyKey,
      accountId: userId,
      fromAsset: fromToken,
      fiatCurrency,
      amount,
      expectedFiatAmount: valuation.targetAmount,
      provider: "real",
      metadata: {
        rate,
        valuation,
        custodyAddress: typeof body.custodyAddress === "string" ? body.custodyAddress : undefined,
      },
    });

    sendJson(response, 202, {
      intentId: result.intentId,
      orderId: result.intentId,
      transactionId: result.intentId,
      traceId: result.traceId,
      executionMode: "intent-based",
      fiatValue: valuation.targetAmount,
      rate,
      status: result.status,
      fiatRoute: result.fiatRoute ?? "EUR-SEPA",
      twap: result.twap,
      statusUrl: `/orders/${result.intentId}`,
    });
    return;
  }

  if (method === "POST" && url.pathname === "/fireblocks/transactions") {
    await app.store.ready();
    const body = await readJson<Record<string, unknown>>(request);
    const idempotencyKey = requireIdempotencyKey(request.headers, body);
    assertRealExecution({ executionMode: body.executionMode ?? "real" });
    const assetId = stringValue(body.assetId ?? body.settlementAssetId ?? process.env.FIREBLOCKS_NENO_ASSET_ID);
    const result = await app.fireblocksService.createVaultTransfer({
      idempotencyKey,
      orderId: optionalString(body.orderId ?? body.transactionId),
      accountId: stringValue(body.accountId ?? body.userId ?? "fireblocks-treasury"),
      assetId,
      amount: stringValue(body.amount),
      destinationWallet: stringValue(body.destinationWallet ?? body.wallet ?? body.to),
      destinationTag: optionalString(body.destinationTag ?? body.tag),
      purpose: body.purpose === "settlement" || body.purpose === "treasury-transfer" ? body.purpose : "offramp",
      fromAsset: optionalString(body.fromAsset ?? body.fromToken ?? assetId),
      toAsset: optionalString(body.toAsset ?? body.toToken ?? assetId),
      chainId: optionalNumber(body.chainId),
      liquidityProvider: optionalString(body.liquidityProvider),
      quoteProvider: optionalString(body.quoteProvider),
      quoteId: optionalString(body.quoteId),
      metadata: body.metadata && typeof body.metadata === "object" && !Array.isArray(body.metadata) ? (body.metadata as Record<string, unknown>) : {},
    });
    sendJson(response, 202, result);
    return;
  }

  if (method === "POST" && url.pathname === "/offramp/fireblocks") {
    await app.store.ready();
    const body = await readJson<Record<string, unknown>>(request);
    const idempotencyKey = requireIdempotencyKey(request.headers, body);
    assertRealExecution({ executionMode: body.executionMode ?? "real" });
    const fromToken = stringValue(body.fromToken ?? body.fromAsset ?? "NENO");
    const assetId = stringValue(
      body.settlementAssetId ??
        body.assetId ??
        (fromToken === "NENO" ? process.env.FIREBLOCKS_NENO_ASSET_ID : process.env.FIREBLOCKS_STABLECOIN_ASSET_ID),
    );
    if (!assetId) {
      throw new Error("Fireblocks offramp requires settlementAssetId/assetId or FIREBLOCKS_NENO_ASSET_ID/FIREBLOCKS_STABLECOIN_ASSET_ID");
    }
    if (
      fromToken !== assetId &&
      body.quoteProvider === undefined &&
      body.liquidityProvider === undefined &&
      body.allowDirectCustomTokenTransfer !== true
    ) {
      throw new Error("INSUFFICIENT_REAL_LIQUIDITY: Fireblocks cannot mark an offramp swap without a real 0x/1inch/OTC quote and executable transfer asset");
    }
    const result = await app.fireblocksService.createVaultTransfer({
      idempotencyKey,
      orderId: optionalString(body.orderId ?? body.transactionId),
      accountId: stringValue(body.accountId ?? body.userId ?? "massi-prod-001"),
      assetId,
      amount: stringValue(body.settlementAmount ?? body.amount),
      destinationWallet: stringValue(body.destinationWallet ?? body.wallet),
      destinationTag: optionalString(body.destinationTag ?? body.tag),
      purpose: "offramp",
      fromAsset: fromToken,
      toAsset: stringValue(body.toAsset ?? body.settlementAsset ?? assetId),
      chainId: optionalNumber(body.chainId),
      liquidityProvider: optionalString(body.liquidityProvider),
      quoteProvider: optionalString(body.quoteProvider),
      quoteId: optionalString(body.quoteId),
      metadata: {
        fiatCurrency: body.fiatCurrency ?? "crypto-native",
        payoutPolicy: "fireblocks_completed_plus_chain_confirmations_only",
        destinationWallet: body.destinationWallet ?? body.wallet,
      },
    });
    sendJson(response, 202, result);
    return;
  }

  if (method === "POST" && url.pathname === "/webhooks/fireblocks") {
    await app.store.ready();
    const rawBody = await readRawBody(request);
    const result = await app.fireblocksService.handleWebhook(rawBody, request.headers);
    await app.bus.drain();
    sendJson(response, 202, result);
    return;
  }

  if (method === "GET" && url.pathname.startsWith("/offramp/status/")) {
    await app.store.ready();
    const orderId = decodeURIComponent(url.pathname.replace("/offramp/status/", ""));
    sendJson(response, 200, await app.fireblocksService.status(orderId));
    return;
  }

  if (method === "GET" && url.pathname.startsWith("/orders/")) {
    const transactionId = decodeURIComponent(url.pathname.replace("/orders/", ""));
    sendJson(response, 200, await orderStatus(app, transactionId));
    return;
  }

  if (method === "GET" && url.pathname.startsWith("/reconciliation/")) {
    const transactionId = decodeURIComponent(url.pathname.replace("/reconciliation/", ""));
    const report = await app.reconciliationEngine.reconcile(transactionId);
    await app.bus.drain();
    sendJson(response, 200, report);
    return;
  }

  if (method === "GET" && url.pathname.startsWith("/events/")) {
    const transactionId = decodeURIComponent(url.pathname.replace("/events/", ""));
    sendJson(response, 200, { transactionId, events: app.store.events.byTransaction(transactionId) });
    return;
  }

  if (method === "GET" && url.pathname.startsWith("/ledger/balance/")) {
    const accountId = decodeURIComponent(url.pathname.replace("/ledger/balance/", ""));
    sendJson(response, 200, { accountId, balances: app.ledgerService.balance(accountId) });
    return;
  }

  if (method === "GET" && url.pathname.startsWith("/settlement/proofs/")) {
    const transactionId = decodeURIComponent(url.pathname.replace("/settlement/proofs/", ""));
    sendJson(response, 200, {
      transactionId,
      proofs: app.store.settlementProofs.byTransaction(transactionId),
      hashChain: app.store.settlementProofs.verifyHashChain(),
    });
    return;
  }

  sendJson(response, 404, { error: "not_found" });
}

async function orderStatus(app: App, transactionId: string): Promise<Record<string, unknown>> {
  const events = app.store.events.byTransaction(transactionId);
  if (events.length === 0) return { transactionId, status: "not_found", integrity: false };
  const report = await app.reconciliationEngine.reconcile(transactionId);
  await app.bus.drain();
  const latestEvents = app.store.events.byTransaction(transactionId);
  const failure = latestEvents.find((event) => event.type === "execution.failed" || event.type === "settlement.failed");
  const initiated = latestEvents.find((event) => event.type === "settlement.initiated");
  const pending = latestEvents.find((event) => event.type === "settlement.pending_confirmation");
  const confirmed = latestEvents.find((event) => event.type === "settlement.confirmed");
  const created = latestEvents.find((event) => event.type === "execution.intent_created" || event.type === "orders.created");
  return {
    orderId: transactionId,
    transactionId,
    traceId: String(created?.payload.traceId ?? ""),
    status: failure
      ? "failed"
      : confirmed
        ? "settlement_confirmed"
        : pending
          ? "settlement_pending_confirmation"
          : latestEvents.some((event) => event.type === "execution.completed")
            ? "execution_completed"
            : latestEvents.some((event) => event.type === "execution.started")
              ? "execution_started"
              : latestEvents.some((event) => event.type === "execution.scheduled")
                ? "scheduled"
                : "accepted",
    failureClassification: failure ? classifyFailure(String(failure.payload.reason ?? failure.payload.error ?? "")) : undefined,
    txHash: initiated?.payload.txHash,
    settlementId: initiated?.payload.settlementId,
    integrity: report.integrity,
    reconciliationStatus: report.status,
    state: report.state,
    events: latestEvents.map((event) => ({ eventId: event.eventId, type: event.type, timestamp: event.timestamp })),
    errors: report.errors,
  };
}

function classifyFailure(reason: string): "INSUFFICIENT_LIQUIDITY" | "GAS_REVERT" | "MIN_OUT_NOT_MET" | "SETTLEMENT_TIMEOUT" | "UNKNOWN" {
  if (/quote below protected minOut|minOut/i.test(reason)) return "MIN_OUT_NOT_MET";
  if (/REJECTED_INSUFFICIENT_LIQUIDITY|liquidity/i.test(reason)) return "INSUFFICIENT_LIQUIDITY";
  if (/OFFRAMP_PREFLIGHT_FAILED|revert|CALL_EXCEPTION|estimateGas|execution reverted/i.test(reason)) return "GAS_REVERT";
  if (/SETTLEMENT_TIMEOUT|timeout|not reached|pending|confirmations/i.test(reason)) return "SETTLEMENT_TIMEOUT";
  return "UNKNOWN";
}

async function assertProductionReady(app: App, scope: FlowScope): Promise<void> {
  const report = await productionPreflightReport(app, scope);
  const checks = report.checks as Array<{ name: string; ok: boolean; detail: string }>;
  const failed = checks.filter((check) => !check.ok);
  if (failed.length > 0) {
    throw new Error(`Production preflight failed: ${failed.map((check) => `${check.name}(${check.detail})`).join(", ")}`);
  }
  await app.store.ready();
}

async function productionPreflightReport(app: App, scope: FlowScope): Promise<Record<string, unknown>> {
  const base = app.productionPreflightService.report(scope) as Record<string, unknown> & {
    checks: Array<{ name: string; ok: boolean; detail: string }>;
  };
  const checks = [...base.checks];
  if (process.env.PERSISTENCE_DRIVER === "postgres") {
    const postgres = await safePostgresStatus(app);
    checks.push({
      name: "postgresConnectivity",
      ok: postgres.enabled === true && !postgres.error,
      detail: postgres.error ? String(postgres.error) : "PostgreSQL schema verified",
    });
  }
  const ready = checks.every((check) => check.ok);
  return {
    ...base,
    checks,
    ready,
    productionFlowAllowed: ready,
  };
}

async function safePostgresStatus(app: App): Promise<Record<string, unknown>> {
  try {
    return await app.store.postgresStatus();
  } catch (error) {
    return {
      enabled: process.env.PERSISTENCE_DRIVER === "postgres",
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function flowScope(url: URL): FlowScope {
  const flow = url.searchParams.get("flow");
  return flow === "swap" || flow === "offramp" ? flow : "all";
}

function assertRealExecution(body: Record<string, unknown>): void {
  const mode = stringValue(body.executionMode ?? "real");
  if (mode !== "real") {
    throw new Error("Only executionMode=real is supported; placeholder execution is disabled");
  }
}

function stringValue(value: unknown): string {
  return String(value ?? "");
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function optionalNumber(value: unknown): number | undefined {
  const parsed = typeof value === "number" ? value : typeof value === "string" && value.length > 0 ? Number(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : undefined;
}

function assertPositiveDecimal(value: string, label: string): void {
  if (!/^\d+(\.\d+)?$/.test(value) || Number(value) <= 0) {
    throw new Error(`${label} must be a positive decimal string`);
  }
}

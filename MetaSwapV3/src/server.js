import http from "node:http";
import { readFile } from "node:fs/promises";
import { loadEnvFile } from "./env-file.js";
import { createPlatform } from "./platform.js";

loadEnvFile();
const platform = createPlatform();
const port = Number(process.env.PORT ?? 8080);
const host = process.env.HOST ?? "127.0.0.1";

function send(res, status, body) {
  res.writeHead(status, secureHeaders({ "content-type": "application/json; charset=utf-8" }));
  res.end(JSON.stringify(body, null, 2));
}

function sendText(res, status, body, contentType = "text/plain; charset=utf-8") {
  res.writeHead(status, secureHeaders({ "content-type": contentType }));
  res.end(body);
}

async function readJson(req) {
  let raw = "";
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > 1_000_000) throw new Error("Request body too large");
  }
  return raw ? JSON.parse(raw) : {};
}

function secureHeaders(headers) {
  return {
    ...headers,
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "content-security-policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'",
    "cache-control": "no-store"
  };
}

function requireAdmin(req) {
  const expected = platform.config.security.adminApiKey;
  if (!expected) return;
  if (req.headers["x-admin-api-key"] !== expected) throw new Error("Admin authorization failed");
}

function apiKey(req) {
  const header = req.headers["x-api-key"] ?? req.headers.authorization;
  if (!header) return undefined;
  return String(header).replace(/^Bearer\s+/i, "");
}

const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);
    const method = req.method ?? "GET";

    if (method === "GET" && url.pathname === "/") {
      return sendText(res, 200, await readFile(new URL("../public/index.html", import.meta.url), "utf8"), "text/html; charset=utf-8");
    }
    if (method === "GET" && url.pathname === "/wallet") {
      return sendText(res, 200, await readFile(new URL("../public/wallet.html", import.meta.url), "utf8"), "text/html; charset=utf-8");
    }
    if (method === "GET" && url.pathname === "/developers") {
      return sendText(res, 200, await readFile(new URL("../public/developers.html", import.meta.url), "utf8"), "text/html; charset=utf-8");
    }
    if (method === "GET" && url.pathname === "/enterprise") {
      return sendText(res, 200, await readFile(new URL("../public/enterprise.html", import.meta.url), "utf8"), "text/html; charset=utf-8");
    }
    if (method === "GET" && url.pathname === "/health") return send(res, 200, { status: "ok", service: "metaswap-v3-core" });
    if (method === "GET" && url.pathname === "/metrics") return sendText(res, 200, platform.metricsService.prometheus());
    if (method === "GET" && url.pathname === "/revenue/summary") {
      const target = url.searchParams.get("targetMonthlyUsd") ?? process.env.REVENUE_TARGET_MONTHLY_USD ?? 1_000_000;
      return send(res, 200, platform.revenueEngine.summary({ targetMonthlyUsd: Number(target) }));
    }
    if (method === "GET" && url.pathname === "/revenue/scale-plan") return send(res, 200, platform.revenueEngine.scalePlan());
    if (method === "GET" && url.pathname === "/revenue/distribution/plan") return send(res, 200, platform.revenueDistributionEngine.plan());
    if (method === "GET" && url.pathname === "/revenue/distribution/status") return send(res, 200, platform.revenueDistributionEngine.distributions);
    if (method === "GET" && url.pathname === "/growth/summary") return send(res, 200, platform.growthEngine.summary());
    if (method === "GET" && url.pathname === "/growth/campaigns") return send(res, 200, platform.growthEngine.campaigns);
    if (method === "GET" && url.pathname === "/enterprise/packages") return send(res, 200, platform.enterpriseSalesEngine.packages);
    if (method === "GET" && url.pathname === "/enterprise/summary") return send(res, 200, platform.enterpriseSalesEngine.summary());
    if (method === "GET" && url.pathname === "/enterprise/forecast") return send(res, 200, platform.enterpriseSalesEngine.forecast({ horizonHours: Number(url.searchParams.get("horizonHours") ?? 72) }));
    if (method === "GET" && url.pathname === "/enterprise/outbound-assets") return send(res, 200, platform.enterpriseSalesEngine.outboundSequences);
    if (method === "GET" && url.pathname === "/enterprise/leads") { requireAdmin(req); return send(res, 200, platform.enterpriseSalesEngine.leads); }
    if (method === "GET" && url.pathname === "/enterprise/proposals") { requireAdmin(req); return send(res, 200, platform.enterpriseSalesEngine.proposals); }
    if (method === "GET" && url.pathname === "/developer/plans") return send(res, 200, platform.developerPlatform.plans);
    if (method === "GET" && url.pathname === "/developer/me") return send(res, 200, platform.developerPlatform.dashboard({ apiKey: apiKey(req) }));
    if (method === "GET" && url.pathname === "/developer/summary") { requireAdmin(req); return send(res, 200, platform.developerPlatform.summary()); }
    if (method === "GET" && url.pathname === "/developer/invoices") { requireAdmin(req); return send(res, 200, platform.developerPlatform.quoteInvoice({ customerId: url.searchParams.get("customerId") })); }
    if (method === "GET" && url.pathname === "/webhooks/summary") { requireAdmin(req); return send(res, 200, platform.webhookService.summary()); }
    if (method === "GET" && url.pathname === "/rpc/products") return send(res, 200, platform.rpcMonetizationService.summary());
    if (method === "GET" && url.pathname === "/analytics/anomalies") { requireAdmin(req); return send(res, 200, platform.anomalyDetectionService.report()); }
    if (method === "GET" && url.pathname === "/assets") return send(res, 200, platform.assetRegistry.list());
    if (method === "GET" && url.pathname === "/events") return send(res, 200, platform.eventBus.tail(Number(url.searchParams.get("limit") ?? 100)));
    if (method === "GET" && url.pathname === "/compliance/cases") return send(res, 200, platform.complianceHub.cases);
    if (method === "GET" && url.pathname === "/reconciliation") return send(res, 200, platform.fiatGateway.reconciliation);
    if (method === "GET" && url.pathname === "/proof/reserves-liabilities") return send(res, 200, platform.proofService.reservesAndLiabilities());
    if (method === "GET" && url.pathname === "/travel-rule/messages") return send(res, 200, platform.travelRuleBroker.messages);
    if (method === "GET" && url.pathname === "/settlement/status") return send(res, 200, platform.settlementOrchestrator.status());
    if (method === "GET" && url.pathname === "/rpc/status") return send(res, 200, Object.fromEntries(Object.entries(platform.onChainSettlement.blockchainAdapters).map(([chain, adapter]) => [chain, adapter.status()])));
    if (method === "GET" && url.pathname === "/soc/incidents") return send(res, 200, platform.incidentResponse.incidents);
    if (method === "GET" && url.pathname === "/compliance/regulatory") return send(res, 200, platform.regulatoryWorkflow.status());
    if (method === "GET" && url.pathname === "/providers") return send(res, 200, platform.providerRegistry.list());
    if (method === "GET" && url.pathname === "/secrets/status") { requireAdmin(req); return send(res, 200, platform.secretLifecycle.status()); }
    if (method === "GET" && url.pathname === "/regions/status") return send(res, 200, platform.multiRegionOrchestrator.status());
    if (method === "GET" && url.pathname.startsWith("/wallets/portfolio/")) {
      return send(res, 200, await platform.portfolioEngine.portfolio(url.pathname.split("/").pop()));
    }
    if (method === "GET" && url.pathname.startsWith("/wallets/token-import/")) {
      const [, , , symbol, chain] = url.pathname.split("/");
      return send(res, 200, platform.walletService.tokenImportMetadata(platform.assetRegistry.get(symbol.toUpperCase()), chain));
    }
    if (method === "GET" && url.pathname.startsWith("/treasury/exposure/")) {
      return send(res, 200, platform.treasuryService.exposure(url.pathname.split("/").pop().toUpperCase()));
    }
    if (method === "GET" && url.pathname.startsWith("/ledger/balances/")) {
      return send(res, 200, platform.ledger.balancesForOwner(url.pathname.split("/").pop()));
    }
    if (method === "GET" && url.pathname.startsWith("/market-depth/")) {
      return send(res, 200, platform.matchingEngine.depth(url.pathname.split("/").pop().toUpperCase()));
    }

    if (method === "POST" && url.pathname === "/users") return send(res, 201, platform.complianceHub.upsertUser(await readJson(req)));
    if (method === "POST" && url.pathname === "/tokens") return send(res, 201, await platform.tokenFactory.createToken(await readJson(req)));
    if (method === "POST" && url.pathname === "/growth/leads") return send(res, 201, platform.growthEngine.captureLead(await readJson(req)));
    if (method === "POST" && url.pathname === "/growth/referrals") return send(res, 201, platform.growthEngine.recordReferral(await readJson(req)));
    if (method === "POST" && url.pathname === "/enterprise/leads") return send(res, 201, platform.enterpriseSalesEngine.captureLead(await readJson(req)));
    if (method === "POST" && url.pathname === "/enterprise/proposals") return send(res, 201, platform.enterpriseSalesEngine.createProposal(await readJson(req)));
    if (method === "POST" && url.pathname === "/enterprise/touches") { requireAdmin(req); return send(res, 201, platform.enterpriseSalesEngine.recordTouch(await readJson(req))); }
    if (method === "POST" && url.pathname === "/enterprise/payments") { requireAdmin(req); return send(res, 201, platform.enterpriseSalesEngine.recordVerifiedPayment(await readJson(req))); }
    if (method === "POST" && url.pathname === "/developer/onboard") return send(res, 201, platform.developerPlatform.onboard(await readJson(req)));
    if (method === "POST" && url.pathname === "/developer/api-keys") { requireAdmin(req); return send(res, 201, platform.developerPlatform.registerApiKey(await readJson(req))); }
    if (method === "POST" && url.pathname === "/developer/subscriptions") { requireAdmin(req); return send(res, 201, platform.developerPlatform.subscribe(await readJson(req))); }
    if (method === "POST" && url.pathname === "/webhooks") return send(res, 201, platform.webhookService.subscribe({ ...await readJson(req), apiKey: apiKey(req) }));
    if (method === "POST" && url.pathname === "/webhooks/flush") { requireAdmin(req); return send(res, 201, await platform.webhookService.flush(await readJson(req))); }
    if (method === "POST" && url.pathname === "/rpc/proxy") return send(res, 201, await platform.rpcMonetizationService.rpc({ ...await readJson(req), apiKey: apiKey(req), ip: req.socket.remoteAddress }));
    if (method === "POST" && url.pathname === "/tx/acceleration/quote") return send(res, 201, platform.rpcMonetizationService.accelerationQuote(await readJson(req)));
    if (method === "POST" && url.pathname === "/tx/relay") return send(res, 201, await platform.rpcMonetizationService.relay({ ...await readJson(req), apiKey: apiKey(req), ip: req.socket.remoteAddress }));
    if (method === "POST" && url.pathname === "/orders") return send(res, 201, await platform.oms.submitOrder(await readJson(req)));
    if (method === "POST" && url.pathname === "/revenue/distribution/sweep") { requireAdmin(req); return send(res, 201, await platform.revenueDistributionEngine.sweep(await readJson(req))); }
    if (method === "POST" && url.pathname === "/fiat/deposit") return send(res, 201, platform.fiatGateway.deposit(await readJson(req)));
    if (method === "POST" && url.pathname === "/fiat/payout") return send(res, 201, await platform.fiatGateway.payout(await readJson(req)));
    if (method === "POST" && url.pathname === "/custody/withdraw") return send(res, 201, await platform.custodyService.withdraw(await readJson(req)));
    if (method === "POST" && url.pathname === "/admin/markets/halt") { requireAdmin(req); return send(res, 201, platform.adminControlPlane.haltMarket(await readJson(req))); }
    if (method === "POST" && url.pathname === "/admin/markets/resume") { requireAdmin(req); return send(res, 201, platform.adminControlPlane.resumeMarket(await readJson(req))); }
    if (method === "POST" && url.pathname === "/admin/stress-test") { requireAdmin(req); return send(res, 201, platform.adminControlPlane.stressTest(await readJson(req))); }
    if (method === "POST" && url.pathname === "/admin/reconcile") { requireAdmin(req); return send(res, 201, platform.adminControlPlane.reconcile()); }
    if (method === "POST" && url.pathname === "/soc/incidents") { requireAdmin(req); return send(res, 201, platform.incidentResponse.trigger(await readJson(req))); }
    if (method === "POST" && url.pathname === "/compliance/evidence") { requireAdmin(req); return send(res, 201, platform.regulatoryWorkflow.attachEvidence(await readJson(req))); }
    if (method === "POST" && url.pathname === "/compliance/evidence/generate") { requireAdmin(req); return send(res, 201, platform.evidenceGenerator.generate((await readJson(req)).control)); }
    if (method === "POST" && url.pathname === "/providers/status") { requireAdmin(req); return send(res, 201, platform.providerRegistry.setStatus(await readJson(req))); }
    if (method === "POST" && url.pathname === "/secrets/seal") { requireAdmin(req); return send(res, 201, platform.secretLifecycle.seal(await readJson(req))); }
    if (method === "POST" && url.pathname === "/regions/failover") { requireAdmin(req); return send(res, 201, platform.multiRegionOrchestrator.failover(await readJson(req))); }
    if (method === "POST" && url.pathname === "/wallets/challenge") return send(res, 201, platform.walletService.createChallenge(await readJson(req)));
    if (method === "POST" && url.pathname === "/wallets/verify") return send(res, 201, platform.walletService.verifyChallenge(await readJson(req)));
    if (method === "POST" && url.pathname === "/onchain/gas-estimate") return send(res, 201, await platform.onChainSettlement.estimateGas(await readJson(req)));
    if (method === "POST" && url.pathname === "/onchain/broadcast") return send(res, 201, await platform.onChainSettlement.broadcast(await readJson(req)));
    if (method === "POST" && url.pathname === "/tokens/deployment/prepare") return send(res, 201, await platform.tokenDeploymentService.prepare(await readJson(req)));
    if (method === "POST" && url.pathname === "/onchain/deposits/scan") return send(res, 201, await platform.blockchainEventListener.scanDeposits(await readJson(req)));
    if (method === "POST" && url.pathname === "/onchain/deposits/sync") return send(res, 201, await platform.blockchainEventListener.syncDeposits(await readJson(req)));

    return send(res, 404, { error: "not_found" });
  } catch (error) {
    return send(res, 400, { error: error.message });
  }
});

server.listen(port, host, () => {
  console.log(`MetaSwap V3 core listening on http://${host}:${port}`);
});

export { server, platform };

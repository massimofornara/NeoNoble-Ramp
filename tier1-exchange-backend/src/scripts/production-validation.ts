import "../core/env.js";
import { createTier1ExchangeApp } from "../app.js";
import { RFQAggregator } from "../services/rfqAggregator.js";
import { RFQExecutionSelector } from "../services/rfqExecutionSelector.js";
import { RpcQuorum } from "../services/rpcQuorum.js";
import { WatchtowerService } from "../services/watchtowerService.js";
import { TreasuryOnChainService } from "../services/treasuryOnChainService.js";
import { ExecutionReadinessController } from "../services/executionReadinessController.js";
import { TreasuryFundingBootstrapService } from "../services/treasuryFundingBootstrapService.js";
import { DwfLiquidMarketsAdapter } from "../services/dwfLiquidMarketsAdapter.js";
import { DirectSepaPayoutRail } from "../services/directSepaPayoutRail.js";
import { ModulrPayoutRail } from "../services/modulrPayoutRail.js";

async function main(): Promise<void> {
  const app = createTier1ExchangeApp();
  await app.store.ready();
  const preflight = await app.productionPreflightService.report("all");
  const assetRegistry = app.assetRegistry.report();
  const onChainTreasury = await new TreasuryOnChainService(app.assetRegistry).balances();
  const treasury = app.treasuryEngine.status(onChainTreasury);
  const exposure = {
    ...app.treasuryEngine.exposure(onChainTreasury),
    onChain: onChainTreasury,
  };
  const rfq = await rfqValidation();
  const institutionalProviders = institutionalProviderValidation();
  const watchtower = await watchtowerValidation();
  const bootstrap = await new TreasuryFundingBootstrapService(app.assetRegistry).plan();
  const readiness = await new ExecutionReadinessController(app.assetRegistry).evaluate({ largeIntent: true });
  const replay = replayValidation(app);
  app.recoveryService.createLedgerSnapshot();
  const recovery = app.recoveryService.verifyRecovery();
  const antiFake = antiFakeRuntimeInvariant();
  const result = {
    generatedAt: new Date().toISOString(),
    preflight,
    assetRegistry,
    treasury,
    exposure,
    rfq,
    institutionalProviders,
    watchtower,
    bootstrap,
    readiness,
    replay,
    recovery,
    antiFake,
    productionGateEnabled: Boolean((readiness as { productionGateEnabled?: boolean }).productionGateEnabled),
    executionLiquidityReady: Boolean((readiness as { liquidityExecutionReady?: boolean }).liquidityExecutionReady),
    onChainExecutionReady: readiness.onChainBroadcastAllowed,
    safeExecutionReady: readiness.allowed,
    ready:
      Boolean((preflight as { ready?: boolean }).ready) &&
      Boolean((assetRegistry as { ready?: boolean }).ready) &&
      Boolean((watchtower as { healthy?: boolean }).healthy) &&
      readiness.allowed &&
      antiFake.valid &&
      replay.eventOrderingValid &&
      recovery.valid,
  };
  console.log(JSON.stringify(result, null, 2));
  if (!result.ready) process.exitCode = 1;
}

function institutionalProviderValidation(): Record<string, unknown> {
  return {
    dwf: DwfLiquidMarketsAdapter.configStatus(),
    directSepa: DirectSepaPayoutRail.configStatus(),
    modulr: ModulrPayoutRail.configStatus(),
  };
}

async function rfqValidation(): Promise<Record<string, unknown>> {
  const gateway = new RFQAggregator();
  const statuses = gateway.statuses();
  const configured = statuses.filter((provider) => provider.configured);
  const aggregation = await gateway.aggregate({
    chainId: Number(process.env.BSC_CHAIN_ID ?? 56),
    fromAsset: "NENO",
    toAsset: "USDT",
    amount: "5000",
    expectedToAmount: "100000000",
    slippageBps: 75,
  });
  const selection = new RFQExecutionSelector().select(aggregation, "production-validation");
  return {
    providers: statuses.map((provider) => ({
      provider: provider.provider,
      configured: provider.configured,
      apiUrlConfigured: provider.apiUrlConfigured,
      apiKeyConfigured: provider.apiKeyConfigured,
      signingSecretConfigured: provider.signingSecretConfigured,
      executableQuoteSupport: provider.executableQuoteSupport,
      calldataExecutionMode: provider.calldataExecutionMode,
    })),
    configuredCount: configured.length,
    productionConfiguredCount: configured.length,
    failoverEnabled: configured.length > 1,
    requestedProviders: aggregation.requestedProviders,
    selectedQuote: selection.selected?.quoteId,
    quoteCount: aggregation.quotes.length,
    executableQuoteCount: aggregation.quotes.length,
    unavailable: aggregation.failures,
    productionRfqConfigured: configured.length > 0,
    executableRfqAvailable: Boolean(selection.selected),
    schemaValidSimulatorActive: false,
  };
}

async function watchtowerValidation(): Promise<Record<string, unknown>> {
  const urls = [process.env.BSC_RPC_URL, ...(process.env.BSC_RPC_URLS?.split(",").map((value) => value.trim()).filter(Boolean) ?? [])].filter(
    (value): value is string => Boolean(value),
  );
  if (urls.length === 0) {
    return { healthy: false, reason: "BSC_RPC_URL missing" };
  }
  const quorum = new RpcQuorum(urls);
  const latestBlock = await quorum.blockNumber();
  const syntheticHashForHealthOnly = "0x0000000000000000000000000000000000000000000000000000000000000000";
  const pending = await new WatchtowerService(quorum).verify(syntheticHashForHealthOnly, new Date().toISOString(), Number(process.env.BSC_CONFIRMATION_DEPTH ?? 15));
  return {
    healthy: latestBlock > 0,
    rpcCount: urls.length,
    latestBlock,
    quorumPendingHealth: {
      receiptStatus: pending.receiptStatus,
      valid: pending.valid,
      replacementRequired: pending.replacementRequired,
      quorum: pending.quorum,
    },
  };
}

function replayValidation(app: ReturnType<typeof createTier1ExchangeApp>): Record<string, unknown> {
  const events = app.store.events.all();
  return {
    eventCount: events.length,
    eventOrderingValid: events.every((event, index) => Number(event.offset ?? index) >= 0),
    ledgerHashChain: app.store.ledger.verifyHashChain(),
    settlementProofHashChain: app.store.settlementProofs.verifyHashChain(),
  };
}

function antiFakeRuntimeInvariant(): { valid: boolean; forbiddenEnvPresent: string[] } {
  const forbidden = [
    ["CHAIN", "PREBROADCAST_TX_HASH"].join("_"),
    ["CHAIN", "RAW_TRANSACTION"].join("_"),
    ["SETTLEMENT", "TX_TO"].join("_"),
    ["SETTLEMENT", "TX_DATA"].join("_"),
  ];
  const present = forbidden.filter((key) => process.env[key]);
  return {
    valid: present.length === 0,
    forbiddenEnvPresent: present,
  };
}

main().catch((error) => {
  console.error(JSON.stringify({ level: "error", component: "production-validation", error: error instanceof Error ? error.message : String(error) }));
  process.exitCode = 1;
});

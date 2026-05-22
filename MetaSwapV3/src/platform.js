import { EventBus } from "./core/event-bus.js";
import { Ledger } from "./core/ledger.js";
import { SqliteStore } from "./core/sqlite-store.js";
import { loadConfig } from "./config.js";
import { BankingAdapter, CardAdapter, MpcCustodyAdapter, MarketMakerAdapter, BlockchainRpcAdapter } from "./adapters/external-adapters.js";
import { AssetRegistry } from "./services/asset-registry.js";
import { ComplianceHub } from "./services/compliance-hub.js";
import { RiskEngine } from "./services/risk-engine.js";
import { PricingEngine } from "./services/pricing-engine.js";
import { InternalLiquidityEngine } from "./services/liquidity-engine.js";
import { RfqEngine } from "./services/rfq-engine.js";
import { MatchingEngine } from "./services/matching-engine.js";
import { TokenFactory } from "./services/token-factory.js";
import { FiatGateway } from "./services/fiat-gateway.js";
import { CustodyService } from "./services/custody-service.js";
import { OrderManagementService } from "./services/oms.js";
import { ProofService } from "./services/proof-service.js";
import { TreasuryService } from "./services/treasury-service.js";
import { InternalMarketMaker } from "./services/internal-market-maker.js";
import { CircuitBreaker } from "./services/circuit-breaker.js";
import { SurveillanceEngine } from "./services/surveillance-engine.js";
import { TravelRuleBroker } from "./services/travel-rule-broker.js";
import { ReconciliationEngine } from "./services/reconciliation-engine.js";
import { AdminControlPlane } from "./services/admin-control-plane.js";
import { SelfHostedHsm } from "./services/self-hosted-hsm.js";
import { MetricsService } from "./services/metrics-service.js";
import { SettlementOrchestrator } from "./services/settlement-orchestrator.js";
import { WalletService } from "./services/wallet-service.js";
import { PortfolioEngine } from "./services/portfolio-engine.js";
import { OnChainSettlement } from "./services/onchain-settlement.js";
import { TokenDeploymentService } from "./services/token-deployment-service.js";
import { BlockchainEventListener } from "./services/blockchain-event-listener.js";
import { ProductionGate } from "./services/production-gate.js";
import { IncidentResponse } from "./services/incident-response.js";
import { RegulatoryWorkflow } from "./services/regulatory-workflow.js";
import { ProviderRegistry } from "./services/provider-registry.js";
import { RailOrchestrator } from "./services/rail-orchestrator.js";
import { SecretLifecycle } from "./services/secret-lifecycle.js";
import { EvidenceGenerator } from "./services/evidence-generator.js";
import { MultiRegionOrchestrator } from "./services/multi-region-orchestrator.js";
import { RevenueEngine } from "./services/revenue-engine.js";
import { GrowthEngine } from "./services/growth-engine.js";
import { RevenueDistributionEngine } from "./services/revenue-distribution-engine.js";
import { DeveloperPlatform } from "./services/developer-platform.js";
import { WebhookService } from "./services/webhook-service.js";
import { RpcMonetizationService } from "./services/rpc-monetization-service.js";
import { AnomalyDetectionService } from "./services/anomaly-detection-service.js";
import { EnterpriseSalesEngine } from "./services/enterprise-sales-engine.js";

export function createPlatform(options = {}) {
  const config = options.config ?? loadConfig();
  const store = options.store === false ? undefined : new SqliteStore(config.storage.sqlitePath);
  const eventBus = new EventBus(store);
  const ledger = new Ledger(eventBus, store);
  const assetRegistry = new AssetRegistry(store);

  for (const asset of [
    { symbol: "EUR", name: "Euro", type: "fiat", lifecycle: "liquid" },
    { symbol: "USD", name: "US Dollar", type: "fiat", lifecycle: "liquid" },
    { symbol: "USDT", name: "Tether USD", type: "stablecoin", lifecycle: "liquid" },
    { symbol: "BTC", name: "Bitcoin", type: "crypto", lifecycle: "liquid" },
    { symbol: "ETH", name: "Ether", type: "crypto", lifecycle: "liquid" },
    { symbol: "BNB", name: "BNB", type: "crypto", lifecycle: "liquid" },
    { symbol: "MATIC", name: "Polygon", type: "crypto", lifecycle: "liquid" },
    { symbol: "SOL", name: "Solana", type: "crypto", lifecycle: "liquid" }
  ]) assetRegistry.register(asset);

  const complianceHub = new ComplianceHub(eventBus);
  const pricingEngine = new PricingEngine({ assetRegistry, eventBus });
  const revenueEngine = new RevenueEngine({ ledger, pricingEngine, eventBus });
  const developerPlatform = new DeveloperPlatform({ eventBus, revenueEngine, config: config.developerPlatform });
  const growthEngine = new GrowthEngine({ revenueEngine, eventBus });
  const enterpriseSalesEngine = new EnterpriseSalesEngine({ eventBus, developerPlatform, revenueEngine, growthEngine });
  const treasuryService = new TreasuryService({ ledger, pricingEngine, eventBus });
  const liquidityEngine = new InternalLiquidityEngine({ ledger, pricingEngine, eventBus });
  const bankingAdapter = new BankingAdapter({ ...config.banking, wise: config.wise, requireConfigured: config.external.requireLiveAdapters, eventBus });
  const cardAdapter = new CardAdapter({ ...config.card, requireConfigured: config.external.requireLiveAdapters, eventBus });
  const custodyAdapter = new MpcCustodyAdapter({ ...config.custody, requireConfigured: config.external.requireLiveAdapters, eventBus });
  const marketMakerAdapter = new MarketMakerAdapter({ ...config.marketMaker, requireConfigured: false, eventBus });
  const blockchainAdapters = Object.fromEntries(Object.entries(config.blockchain).map(([chain, cfg]) => [
    chain,
    new BlockchainRpcAdapter({ ...cfg, namespace: chain === "solana" ? "solana" : "evm" })
  ]));
  const webhookService = new WebhookService({ eventBus, developerPlatform, secret: config.developerPlatform.webhookSecret });
  const rpcMonetizationService = new RpcMonetizationService({ blockchainAdapters, developerPlatform, eventBus });
  const internalMarketMaker = new InternalMarketMaker({ pricingEngine, liquidityEngine, treasuryService, eventBus });
  const rfqEngine = new RfqEngine({ pricingEngine, liquidityEngine, eventBus, internalMarketMaker, marketMakerAdapter });
  const matchingEngine = new MatchingEngine(eventBus);
  const providerRegistry = new ProviderRegistry({ eventBus });
  providerRegistry.register({ id: "primary-banking-rail", kind: "fiat_rail", priority: 10, capabilities: ["SEPA", "SWIFT"] });
  providerRegistry.register({ id: "primary-card-rail", kind: "fiat_rail", priority: 20, capabilities: ["CARD"] });
  const railOrchestrator = new RailOrchestrator({ providerRegistry, bankingAdapter, cardAdapter, eventBus });
  const revenueDistributionEngine = new RevenueDistributionEngine({ ledger, pricingEngine, railOrchestrator, eventBus, config: config.distribution });
  const circuitBreaker = new CircuitBreaker(eventBus);
  const surveillanceEngine = new SurveillanceEngine({ complianceHub, eventBus });
  const riskEngine = new RiskEngine({ complianceHub, ledger, assetRegistry, pricingEngine, eventBus });
  const tokenFactory = new TokenFactory({ assetRegistry, ledger, pricingEngine, eventBus, blockchainAdapters });
  const travelRuleBroker = new TravelRuleBroker({ eventBus });
  const fiatGateway = new FiatGateway({ ledger, complianceHub, pricingEngine, eventBus, railOrchestrator, travelRuleBroker, revenueEngine });
  const hsm = new SelfHostedHsm({ masterKey: process.env.INTERNAL_HSM_MASTER_KEY, eventBus });
  const walletService = new WalletService({ eventBus, store });
  const portfolioEngine = new PortfolioEngine({ walletService, assetRegistry, blockchainAdapters, pricingEngine, eventBus });
  const onChainSettlement = new OnChainSettlement({ blockchainAdapters, hsm, eventBus });
  const tokenDeploymentService = new TokenDeploymentService({ blockchainAdapters, eventBus });
  const blockchainEventListener = new BlockchainEventListener({ blockchainAdapters, eventBus, ledger });
  const custodyService = new CustodyService({ ledger, complianceHub, pricingEngine, eventBus, custodyAdapter, hsm });
  const oms = new OrderManagementService({ ledger, assetRegistry, pricingEngine, riskEngine, rfqEngine, matchingEngine, eventBus, circuitBreaker, surveillanceEngine, walletService, custodyService, revenueEngine });
  const proofService = new ProofService({ ledger });
  const reconciliationEngine = new ReconciliationEngine({ ledger, fiatGateway, eventBus });
  const adminControlPlane = new AdminControlPlane({ circuitBreaker, treasuryService, reconciliationEngine, eventBus });
  const incidentResponse = new IncidentResponse({ eventBus, adminControlPlane });
  const regulatoryWorkflow = new RegulatoryWorkflow(eventBus);
  const secretLifecycle = new SecretLifecycle({ masterKey: config.security.internalHsmMasterKey ?? "local-secret-lifecycle-key", eventBus });
  const anomalyDetectionService = new AnomalyDetectionService({ eventBus, ledger, developerPlatform, revenueEngine });
  const metricsService = new MetricsService({ eventBus, ledger, assetRegistry, developerPlatform, revenueEngine, webhookService, enterpriseSalesEngine });
  const settlementOrchestrator = new SettlementOrchestrator({ ledger, fiatGateway, custodyService, eventBus });
  const evidenceGenerator = new EvidenceGenerator({ eventBus, ledger, proofService, regulatoryWorkflow });
  const multiRegionOrchestrator = new MultiRegionOrchestrator({
    eventBus,
    regions: [
      { id: "eu-west-primary", role: "active", priority: 10, endpoint: "metaswap-core.eu-west.internal" },
      { id: "eu-central-secondary", role: "standby", priority: 20, endpoint: "metaswap-core.eu-central.internal" }
    ]
  });
  const productionGate = new ProductionGate({ config, blockchainAdapters });
  productionGate.validate();

  if (options.bootstrap !== false) bootstrapIdentities({ complianceHub });
  if (options.bootstrap !== false && ledger.journal.length === 0) bootstrapCapital({ ledger, matchingEngine, pricingEngine });

  return {
    eventBus,
    ledger,
    assetRegistry,
    complianceHub,
    pricingEngine,
    revenueEngine,
    developerPlatform,
    enterpriseSalesEngine,
    webhookService,
    rpcMonetizationService,
    anomalyDetectionService,
    revenueDistributionEngine,
    growthEngine,
    treasuryService,
    liquidityEngine,
    internalMarketMaker,
    providerRegistry,
    railOrchestrator,
    rfqEngine,
    matchingEngine,
    circuitBreaker,
    surveillanceEngine,
    riskEngine,
    tokenFactory,
    travelRuleBroker,
    fiatGateway,
    custodyService,
    hsm,
    walletService,
    portfolioEngine,
    onChainSettlement,
    tokenDeploymentService,
    blockchainEventListener,
    oms,
    proofService,
    reconciliationEngine,
    adminControlPlane,
    incidentResponse,
    regulatoryWorkflow,
    secretLifecycle,
    evidenceGenerator,
    multiRegionOrchestrator,
    metricsService,
    settlementOrchestrator,
    productionGate,
    config
  };
}

function bootstrapIdentities({ complianceHub }) {
  complianceHub.upsertUser({ id: "user-eu-1", name: "Primary User", kycTier: "enhanced", jurisdiction: "EU", clusterId: "cluster-primary" });
  complianceHub.upsertUser({ id: "issuer-1", name: "Primary Issuer", kycTier: "institutional", jurisdiction: "EU", clusterId: "cluster-issuer" });
}

function bootstrapCapital({ ledger, matchingEngine, pricingEngine }) {
  for (const [asset, amount] of Object.entries({ EUR: 10_000_000, USD: 10_000_000, USDT: 5_000_000, BTC: 100, ETH: 5000, BNB: 10000, MATIC: 1_000_000, SOL: 100000 })) {
    const external = ledger.ensureAccount("external", "initial-capital", asset);
    ledger.credit(external, "available", amount);
    const platform = ledger.ensureAccount(asset === "EUR" || asset === "USD" ? "platform" : "platform", asset === "EUR" || asset === "USD" ? "treasury" : "inventory", asset);
    ledger.postTransfer({ from: external, to: platform, asset, amount, memo: "platform initial capitalization" });
  }

  for (const [asset, amount] of Object.entries({ EUR: 10000, USDT: 5000 })) {
    const external = ledger.ensureAccount("external", "customer-onboarding", asset);
    ledger.credit(external, "available", amount);
    const user = ledger.ensureAccount("customer", "user-eu-1", asset);
    ledger.postTransfer({ from: external, to: user, asset, amount, memo: "customer onboarding funding" });
  }

  const ethEur = pricingEngine.midPrice("ETH", "EUR");
  const btcEur = pricingEngine.midPrice("BTC", "EUR");
  matchingEngine.addRestingOrder({ market: "ETH-EUR", ownerId: "platform-inventory", side: "sell", price: ethEur * 1.002, amount: 100 });
  matchingEngine.addRestingOrder({ market: "ETH-EUR", ownerId: "platform-inventory", side: "buy", price: ethEur * 0.998, amount: 100 });
  matchingEngine.addRestingOrder({ market: "BTC-EUR", ownerId: "platform-inventory", side: "sell", price: btcEur * 1.002, amount: 5 });
  matchingEngine.addRestingOrder({ market: "BTC-EUR", ownerId: "platform-inventory", side: "buy", price: btcEur * 0.998, amount: 5 });
}

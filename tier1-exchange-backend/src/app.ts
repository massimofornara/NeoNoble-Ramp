import "./core/env.js";
import { KafkaCompatibleEventStream } from "./core/eventBus.js";
import { ExchangeStore } from "./core/store.js";
import { ComplianceService } from "./services/complianceService.js";
import { ExecutionEngine } from "./services/executionEngine.js";
import { ExecutionControlPlane } from "./services/executionControlPlane.js";
import { ExecutionPlanner } from "./services/executionPlanner.js";
import { IntentService } from "./services/intentService.js";
import { LedgerService } from "./services/ledgerService.js";
import { OrderService } from "./services/orderService.js";
import { ReconciliationEngine } from "./services/reconciliationEngine.js";
import { SettlementEngine } from "./services/settlementEngine.js";
import { SolverEngine } from "./services/solverEngine.js";
import { WalletService } from "./services/walletService.js";
import { AuditService } from "./services/auditService.js";
import { AsyncRiskEngine } from "./services/asyncRiskEngine.js";
import { RiskService } from "./services/riskService.js";
import { SecurityService } from "./services/securityService.js";
import { RecoveryService } from "./services/recoveryService.js";
import { DeterministicMatchingEngine } from "./services/matchingEngine.js";
import { ProductionPreflightService } from "./services/productionPreflightService.js";
import { TreasuryEngine } from "./services/treasuryEngine.js";
import { MpcWalletSigner } from "./services/mpcWalletSigner.js";
import { AssetRegistry } from "./services/assetRegistry.js";
import { FireblocksService } from "./services/fireblocksService.js";
import { join } from "node:path";

export interface Tier1ExchangeApp {
  store: ExchangeStore;
  bus: KafkaCompatibleEventStream;
  orderService: OrderService;
  intentService: IntentService;
  executionPlanner: ExecutionPlanner;
  solverEngine: SolverEngine;
  executionEngine: ExecutionEngine;
  executionControlPlane: ExecutionControlPlane;
  settlementEngine: SettlementEngine;
  ledgerService: LedgerService;
  reconciliationEngine: ReconciliationEngine;
  auditService: AuditService;
  riskService: RiskService;
  asyncRiskEngine: AsyncRiskEngine;
  treasuryEngine: TreasuryEngine;
  mpcWalletSigner: MpcWalletSigner;
  assetRegistry: AssetRegistry;
  securityService: SecurityService;
  recoveryService: RecoveryService;
  matchingEngine: DeterministicMatchingEngine;
  productionPreflightService: ProductionPreflightService;
  fireblocksService: FireblocksService;
}

export function createTier1ExchangeApp(options: { dataDir?: string } = {}): Tier1ExchangeApp {
  const store = new ExchangeStore(options.dataDir);
  const bus = new KafkaCompatibleEventStream(store.events, store.deadLetters, store.consumerOffsets, store.processedEvents);
  const walletService = new WalletService();
  const complianceService = new ComplianceService();
  const riskService = new RiskService(store.events);
  const asyncRiskEngine = new AsyncRiskEngine(bus);
  const executionPlanner = new ExecutionPlanner();
  const solverEngine = new SolverEngine(bus);
  const intentService = new IntentService(bus, store.idempotency, executionPlanner, solverEngine);
  const orderService = new OrderService(bus, store.idempotency, walletService, complianceService, riskService);
  const executionEngine = new ExecutionEngine(bus, store.idempotency);
  const settlementEngine = new SettlementEngine(bus, store.idempotency, store.events, store.settlementProofs);
  const ledgerService = new LedgerService(bus, store.events, store.ledger, store.idempotency);
  const reconciliationEngine = new ReconciliationEngine(bus, store.events, store.ledger, store.settlementProofs);
  const auditService = new AuditService(store.events, store.ledger);
  const securityService = new SecurityService(join(store.paths.dataDir, "security-keys.json"), store.webhookNonces);
  const recoveryService = new RecoveryService(store);
  const matchingEngine = new DeterministicMatchingEngine(bus);
  const productionPreflightService = new ProductionPreflightService();
  const assetRegistry = new AssetRegistry();
  assetRegistry.assertProductionReady();
  const treasuryEngine = new TreasuryEngine(store.ledger);
  const fireblocksService = new FireblocksService(bus, store, reconciliationEngine);
  const executionControlPlane = new ExecutionControlPlane(store.events, store.settlementProofs, treasuryEngine, asyncRiskEngine);
  const mpcWalletSigner = new MpcWalletSigner();
  const snapshotIntervalMs = Number(process.env.SNAPSHOT_INTERVAL_MS ?? 0);
  if (snapshotIntervalMs > 0) {
    const timer = setInterval(() => recoveryService.createLedgerSnapshot(), snapshotIntervalMs);
    timer.unref();
  }

  executionEngine.registerConsumers();
  asyncRiskEngine.registerConsumers();
  settlementEngine.registerConsumers();
  ledgerService.registerConsumers();

  return {
    store,
    bus,
    orderService,
    intentService,
    executionPlanner,
    solverEngine,
    executionEngine,
    executionControlPlane,
    settlementEngine,
    ledgerService,
    reconciliationEngine,
    auditService,
    riskService,
    asyncRiskEngine,
    treasuryEngine,
    mpcWalletSigner,
    assetRegistry,
    securityService,
    recoveryService,
    matchingEngine,
    productionPreflightService,
    fireblocksService,
  };
}

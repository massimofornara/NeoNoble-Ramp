import { AssetRegistry } from "./assetRegistry.js";
import { RFQAggregator } from "./rfqAggregator.js";
import { RpcQuorum } from "./rpcQuorum.js";
import { SorEngine } from "./sorEngine.js";
import { TreasuryFundingBootstrapService } from "./treasuryFundingBootstrapService.js";
import { TreasuryOnChainService } from "./treasuryOnChainService.js";

export interface ExecutionReadiness {
  allowed: boolean;
  status: "ready" | "degraded" | "blocked";
  productionGateEnabled: boolean;
  liquidityExecutionReady: boolean;
  checks: Record<string, boolean>;
  criticalChecks: Record<string, boolean>;
  onChainBroadcastAllowed: boolean;
  degradedExecutionAllowed: boolean;
  degradationPath: string[];
  reasons: string[];
  fallbackPolicy: string[];
  treasury?: Record<string, unknown>;
  bootstrap?: Record<string, unknown>;
}

export class ExecutionReadinessController {
  constructor(
    private readonly registry = new AssetRegistry(),
    private readonly treasury = new TreasuryOnChainService(registry),
    private readonly bootstrap = new TreasuryFundingBootstrapService(registry, treasury),
    private readonly rfqGateway = new RFQAggregator(),
  ) {}

  async evaluate(input: { maxNenoAmount?: string; largeIntent?: boolean } = {}): Promise<ExecutionReadiness> {
    const reasons: string[] = [];
    const assetRegistry = this.assetRegistryReady();
    if (!assetRegistry) reasons.push("asset_registry_invalid");
    const treasury = await this.treasury.balances();
    const treasuryFunded = Boolean((treasury as { fundingSufficientForConfiguredBatch?: boolean }).fundingSufficientForConfiguredBatch);
    if (!treasuryFunded) reasons.push("treasury_not_funded_for_requested_batch");
    const realRfqLayerReady = this.realRfqReady(input.largeIntent ?? Number(input.maxNenoAmount ?? 0) > 5000);
    const embeddedExecutableLiquidityReady = await this.embeddedExecutableLiquidityReady();
    const outputInventoryReady = this.outputInventoryReady(treasury);
    const executableLiquidityReady = realRfqLayerReady || outputInventoryReady || embeddedExecutableLiquidityReady;
    const rfqLayerReady = input.largeIntent || Number(input.maxNenoAmount ?? 0) > 5000 ? realRfqLayerReady || embeddedExecutableLiquidityReady : true;
    if (!rfqLayerReady) reasons.push("rfq_layer_not_ready");
    if (!executableLiquidityReady) reasons.push("executable_liquidity_not_ready");
    const rpcQuorum = await this.rpcQuorumHealthy();
    if (!rpcQuorum) reasons.push("rpc_quorum_unhealthy");
    const watchtowerHealth = rpcQuorum;
    if (!watchtowerHealth) reasons.push("watchtower_unhealthy");
    const checks = {
      treasury_funded: treasuryFunded,
      rfq_layer_ready: rfqLayerReady,
      executable_liquidity_ready: executableLiquidityReady,
      embedded_rfq_sor_ready: embeddedExecutableLiquidityReady,
      output_inventory_ready: outputInventoryReady,
      watchtower_health: watchtowerHealth,
      rpc_quorum: rpcQuorum,
      asset_registry: assetRegistry,
    };
    const criticalChecks = {
      asset_registry: assetRegistry,
      treasury_funded: treasuryFunded,
      rpc_quorum: rpcQuorum,
      watchtower_health: watchtowerHealth,
    };
    const criticalReady = Object.values(criticalChecks).every(Boolean);
    const productionGateEnabled = criticalReady;
    const liquidityExecutionReady = executableLiquidityReady && rfqLayerReady;
    const onChainBroadcastAllowed = productionGateEnabled;
    const degradedExecutionAllowed = productionGateEnabled && !liquidityExecutionReady;
    const allowed = productionGateEnabled;
    return {
      allowed,
      status: !productionGateEnabled ? "blocked" : liquidityExecutionReady ? "ready" : "degraded",
      productionGateEnabled,
      liquidityExecutionReady,
      checks,
      criticalChecks,
      onChainBroadcastAllowed,
      degradedExecutionAllowed,
      degradationPath: this.degradationPath(checks),
      reasons,
      fallbackPolicy: ["rfq-retry", "sor-reroute", "twap-split", "internal-crossing", "amm-last-resort"],
      treasury,
      bootstrap: treasuryFunded ? undefined : await this.bootstrap.plan(),
    };
  }

  private assetRegistryReady(): boolean {
    try {
      this.registry.assertProductionReady();
      return true;
    } catch {
      return false;
    }
  }

  private realRfqReady(required: boolean): boolean {
    if (!required) return true;
    return this.rfqGateway.configuredProviders().length > 0;
  }

  private async embeddedExecutableLiquidityReady(): Promise<boolean> {
    if (!process.env.ZEROX_API_KEY && !process.env.ONEINCH_API_KEY && process.env.DWF_LIQUIDITY_ENABLED !== "true") return false;
    try {
      const decision = await new SorEngine().discover({
        chainId: Number(process.env.BSC_CHAIN_ID ?? process.env.CHAIN_ID ?? 56),
        fromAsset: "NENO",
        toAsset: process.env.READINESS_PROBE_OUTPUT_ASSET ?? "WBNB",
        amount: process.env.READINESS_PROBE_NENO_AMOUNT ?? "50",
        slippageBps: Number(process.env.SWAP_SLIPPAGE_BPS ?? 75),
      });
      return decision.ranked.some((route) => {
        const source = route.quote.liquiditySource;
        return (
          Boolean(route.quote.metadata.executable) &&
          (source === "0x_RFQ" || source === "0x_SWAP" || source === "1inch_fusion" || source === "1inch_swap_v6" || source === "DWF_LIQUID_MARKETS")
        );
      });
    } catch {
      return false;
    }
  }

  private outputInventoryReady(treasury: Record<string, unknown>): boolean {
    const balances = Array.isArray(treasury.balances) ? (treasury.balances as Array<Record<string, unknown>>) : [];
    const groups = [["USDT"], ["USDC"], ["WBNB"], ["ETH", "WETH"], ["BTC", "WBTC"]];
    return groups.every((assets) => assets.some((asset) => this.hasPositiveBalance(balances, asset)));
  }

  private hasPositiveBalance(balances: Array<Record<string, unknown>>, asset: string): boolean {
    const row = balances.find((item) => String(item.asset).toUpperCase() === asset);
    return row ? Number(row.balance ?? 0) > 0 : false;
  }

  private async rpcQuorumHealthy(): Promise<boolean> {
    try {
      const latest = await new RpcQuorum().blockNumber();
      return latest > 0;
    } catch {
      return false;
    }
  }

  private degradationPath(checks: Record<string, boolean>): string[] {
    const path = ["internal-crossing", "adaptive-twap", "sor"];
    if (checks.rfq_layer_ready) path.push("rfq", "otc");
    if (!checks.treasury_funded) path.push("treasury-bootstrap-required");
    if (!checks.rpc_quorum || !checks.watchtower_health) path.push("watchtower-recovery-required");
    return path;
  }
}

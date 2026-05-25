import { productionAssetRegistry } from "./assetRegistry.js";

export interface PreflightCheck {
  name: string;
  ok: boolean;
  detail: string;
}

export type PreflightScope = "all" | "swap" | "offramp";

export class ProductionPreflightService {
  checks(scope: PreflightScope = "all"): PreflightCheck[] {
    const executionMode = String(process.env.BLOCKCHAIN_EXECUTION_MODE ?? "deterministic").toLowerCase();
    const adapter = String(process.env.SETTLEMENT_ADAPTER ?? process.env.DEFAULT_SETTLEMENT_ADAPTER ?? "").toLowerCase();
    const priceMode = String(process.env.PRICE_DISCOVERY_MODE ?? "deterministic").toLowerCase();
    const rpcUrl = adapter === "ethereum" || adapter === "eth" ? process.env.ETHEREUM_RPC_URL : process.env.BSC_RPC_URL;
    const databaseUrlCheck = validateProductionDatabaseUrl(process.env.DATABASE_URL);
    const assetRegistry = productionAssetRegistry().report() as { ready: boolean };
    const commonChecks: PreflightCheck[] = [
      {
        name: "blockchainExecutionMode",
        ok: executionMode === "real",
        detail: `BLOCKCHAIN_EXECUTION_MODE=${executionMode}`,
      },
      {
        name: "settlementAdapter",
        ok: ["bsc", "ethereum", "eth"].includes(adapter),
        detail: `SETTLEMENT_ADAPTER=${adapter}`,
      },
      {
        name: "rpcUrl",
        ok: Boolean(rpcUrl),
        detail: adapter === "ethereum" || adapter === "eth" ? "ETHEREUM_RPC_URL" : "BSC_RPC_URL",
      },
      {
        name: "treasuryAddress",
        ok: Boolean(process.env.TREASURY_ADDRESS),
        detail: "TREASURY_ADDRESS configured",
      },
      {
        name: "treasuryPrivateKey",
        ok: Boolean(process.env.TREASURY_PRIVATE_KEY),
        detail: process.env.TREASURY_PRIVATE_KEY ? "TREASURY_PRIVATE_KEY configured" : "TREASURY_PRIVATE_KEY missing",
      },
      {
        name: "assetRegistry",
        ok: executionMode !== "real" || assetRegistry.ready,
        detail: assetRegistry.ready ? "NENO/USDT/USDC/WBNB/ETH/BTC plus WETH/WBTC wrapped routing configured" : JSON.stringify(assetRegistry),
      },
      {
        name: "postgres",
        ok: process.env.PERSISTENCE_DRIVER === "postgres" && Boolean(process.env.DATABASE_URL),
        detail: `PERSISTENCE_DRIVER=${process.env.PERSISTENCE_DRIVER ?? "file"} DATABASE_URL=${process.env.DATABASE_URL ? "configured" : "missing"}`,
      },
      {
        name: "postgresManagedUrl",
        ok: executionMode !== "real" || databaseUrlCheck.ok,
        detail: databaseUrlCheck.detail,
      },
      {
        name: "priceDiscovery",
        ok: executionMode !== "real" || priceMode === "real",
        detail: `PRICE_DISCOVERY_MODE=${process.env.PRICE_DISCOVERY_MODE ?? "deterministic"}`,
      },
    ];
    const swapChecks: PreflightCheck[] = [
      {
        name: "swapRouter",
        ok: isAddress(process.env.BSC_SWAP_ROUTER_ADDRESS),
        detail: "BSC_SWAP_ROUTER_ADDRESS configured",
      },
    ];
    const offrampChecks: PreflightCheck[] = [
      {
        name: "offrampCustody",
        ok: executionMode !== "real" || isAddress(process.env.OFFRAMP_CUSTODY_ADDRESS),
        detail: "OFFRAMP_CUSTODY_ADDRESS configured for real offramp execution",
      },
    ];
    return [...commonChecks, ...(scope === "offramp" ? offrampChecks : scope === "swap" ? swapChecks : [...swapChecks, ...offrampChecks])];
  }

  assertReady(scope: PreflightScope = "all"): void {
    const failed = this.checks(scope).filter((check) => !check.ok);
    if (failed.length > 0) {
      throw new Error(`Production preflight failed: ${failed.map((check) => `${check.name}(${check.detail})`).join(", ")}`);
    }
  }

  report(scope: PreflightScope = "all"): Record<string, unknown> {
    const checks = this.checks(scope);
    return {
      scope,
      ready: checks.every((check) => check.ok),
      checks,
      productionFlowAllowed: checks.every((check) => check.ok),
      placeholderSettlementAllowed: false,
    };
  }
}

function isAddress(value: string | undefined): boolean {
  return Boolean(value && /^0x[a-fA-F0-9]{40}$/.test(value));
}

function validateProductionDatabaseUrl(value: string | undefined): { ok: boolean; detail: string } {
  if (!value) return { ok: false, detail: "DATABASE_URL missing" };
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return { ok: false, detail: "DATABASE_URL must be a valid PostgreSQL URL" };
  }
  if (!["postgresql:", "postgres:"].includes(parsed.protocol)) {
    return { ok: false, detail: "DATABASE_URL must use postgresql:// or postgres://" };
  }
  const host = parsed.hostname.toLowerCase();
  if (!host || ["postgres", "localhost", "127.0.0.1", "::1"].includes(host)) {
    return { ok: false, detail: "DATABASE_URL must not use localhost or docker hostname postgres" };
  }
  if (!host.endsWith(".neon.tech")) {
    return { ok: false, detail: "DATABASE_URL must use a Neon .neon.tech host" };
  }
  if (parsed.searchParams.get("sslmode") !== "require") {
    return { ok: false, detail: "DATABASE_URL must include sslmode=require" };
  }
  return { ok: true, detail: "Neon DATABASE_URL configured with sslmode=require" };
}

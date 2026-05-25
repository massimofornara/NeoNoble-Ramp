import "../core/env.js";
import { FireblocksClient } from "../services/fireblocksClient.js";

async function main(): Promise<void> {
  const readiness = FireblocksClient.readinessFromEnv();
  if (!readiness.configured) {
    throw new Error(`Fireblocks sandbox check blocked: missing ${readiness.missing.join(", ")}`);
  }
  const client = FireblocksClient.fromEnv();
  const vault = await client.getVaultAccount();
  const assetIds = [process.env.FIREBLOCKS_NENO_ASSET_ID, process.env.FIREBLOCKS_STABLECOIN_ASSET_ID].filter((value): value is string => Boolean(value));
  const balances: Record<string, unknown> = {};
  for (const assetId of assetIds) {
    balances[assetId] = await client.getVaultAssetBalance(client.config.vaultAccountId, assetId);
  }
  console.log(
    JSON.stringify(
      {
        mode: "fireblocks-sandbox-check",
        baseUrl: client.config.baseUrl,
        vaultAccountId: client.config.vaultAccountId,
        vault,
        balances,
      },
      null,
      2,
    ),
  );
}

main().catch((error) => {
  console.error(
    JSON.stringify({
      level: "error",
      component: "fireblocks-sandbox-check",
      error: error instanceof Error ? error.message : String(error),
    }),
  );
  process.exitCode = 1;
});

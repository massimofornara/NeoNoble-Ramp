import "../core/env.js";

import { DwfLiquidMarketsAdapter } from "../services/dwfLiquidMarketsAdapter.js";
import { DirectSepaPayoutRail } from "../services/directSepaPayoutRail.js";
import { ModulrPayoutRail } from "../services/modulrPayoutRail.js";

async function main(): Promise<void> {
  const modulr = new ModulrPayoutRail();
  const directSepa = new DirectSepaPayoutRail();
  const live = process.env.LIVE_PROVIDER_READINESS === "1";
  const modulrConfig = ModulrPayoutRail.configStatus();
  const directSepaConfig = DirectSepaPayoutRail.configStatus();
  const result: Record<string, unknown> = {
    generatedAt: new Date().toISOString(),
    safety: {
      noMockLiquidity: true,
      noSyntheticSettlement: true,
      noForcedPayoutConfirmation: true,
      secretsRedacted: true,
    },
    dwf: DwfLiquidMarketsAdapter.configStatus(),
    directSepa: {
      ...directSepaConfig,
      destination: redactDestination(directSepa.destination()),
      readiness: live ? await directSepa.readiness(process.env.PROVIDER_READINESS_EUR_AMOUNT ?? "1") : "set LIVE_PROVIDER_READINESS=1 to perform balance/API readiness",
    },
    modulr: {
      ...modulrConfig,
      destination: redactDestination(modulr.destination()),
      readiness: live ? await modulr.readiness(process.env.PROVIDER_READINESS_EUR_AMOUNT ?? "1") : "set LIVE_PROVIDER_READINESS=1 to perform balance/API readiness",
    },
    enabledForRuntime: {
      payoutRail: process.env.PAYOUT_RAIL ?? "direct-sepa",
      bankPayoutExecutionMode: process.env.BANK_PAYOUT_EXECUTION_MODE ?? "not_configured",
      directSepaEnabled: process.env.BANK_RAIL_ENABLED === "true" || process.env.SEPA_RAIL_ENABLED === "true",
      dwfLiquidityEnabled: process.env.DWF_LIQUIDITY_ENABLED === "true",
      modulrEnabled: process.env.MODULR_ENABLED === "true" || process.env.MODULR_PAYOUTS_ENABLED === "true",
    },
  };
  console.log(JSON.stringify(result, null, 2));
}

function redactDestination(destination: ReturnType<ModulrPayoutRail["destination"]>): Record<string, string> {
  const compactIban = destination.iban.replace(/\s+/g, "");
  return {
    bank: destination.bank,
    iban: compactIban.length > 8 ? `${compactIban.slice(0, 4)}...${compactIban.slice(-4)}` : "<configured>",
    bic: destination.bic,
    beneficiary: destination.beneficiary,
  };
}

main().catch((error) => {
  console.error(JSON.stringify({ level: "error", component: "provider-readiness", error: error instanceof Error ? error.message : String(error) }));
  process.exitCode = 1;
});

import "../core/env.js";

import { DirectSepaPayoutRail } from "../services/directSepaPayoutRail.js";

async function main(): Promise<void> {
  const rail = new DirectSepaPayoutRail();
  const amount = process.env.DIRECT_SEPA_ACTIVATION_AMOUNT_EUR ?? "1";
  const live = process.env.LIVE_PROVIDER_READINESS === "1";
  const status = DirectSepaPayoutRail.configStatus();
  const readiness = live ? await rail.readiness(amount) : undefined;
  const configured = Boolean(status.configured);
  const ready = Boolean(readiness?.ready);
  const result = {
    generatedAt: new Date().toISOString(),
    mode: "direct-sepa-runtime-activation",
    guardrails: {
      noSyntheticPayoutProof: true,
      noForcedConfiguredTrue: true,
      bankStatusConfirmationRequired: true,
      transferProofRequiresProviderFinalStatus: true,
    },
    destination: redactDestination(rail.destination()),
    configured,
    ready,
    status,
    readiness: readiness ?? "set LIVE_PROVIDER_READINESS=1 to perform provider balance/API readiness",
    activation: {
      runtimeConfiguredTrue: configured && ready,
      transferProofPossible: configured && ready,
      requiredForConfiguredTrue: [
        "BANK_PAYOUT_EXECUTION_MODE=real",
        "BANK_RAIL_ENABLED=true or SEPA_RAIL_ENABLED=true",
        "BANK_RAIL_SUBMIT_URL or SEPA_PAYOUT_API_URL",
        "BANK_RAIL_BALANCE_URL or SEPA_BALANCE_API_URL",
        "BANK_RAIL_STATUS_URL or SEPA_PAYOUT_STATUS_URL",
        "BANK_RAIL_API_KEY or SEPA_PROVIDER_API_KEY",
        "BANK_RAIL_TREASURY_ACCOUNT_ID or SEPA_TREASURY_ACCOUNT_ID",
      ],
    },
  };
  console.log(JSON.stringify(result, null, 2));
  if (!configured || (live && !ready)) process.exitCode = 1;
}

function redactDestination(destination: ReturnType<DirectSepaPayoutRail["destination"]>): Record<string, string> {
  const compactIban = destination.iban.replace(/\s+/g, "");
  return {
    bank: destination.bank,
    iban: compactIban.length > 8 ? `${compactIban.slice(0, 4)}...${compactIban.slice(-4)}` : "<configured>",
    bic: destination.bic,
    beneficiary: destination.beneficiary,
  };
}

main().catch((error) => {
  console.error(JSON.stringify({ level: "error", component: "direct-sepa-activation", error: error instanceof Error ? error.message : String(error) }));
  process.exitCode = 1;
});

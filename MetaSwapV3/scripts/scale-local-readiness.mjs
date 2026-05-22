import { writeFileSync } from "node:fs";
import { loadEnvFile } from "../src/env-file.js";
import { loadConfig } from "../src/config.js";
import { createPlatform } from "../src/platform.js";

const OUTPUT = ".data/scale-readiness.json";

loadEnvFile(".env.production");
const config = loadConfig();
const platform = createPlatform({ config });
const targetMonthlyUsd = Number(process.env.REVENUE_TARGET_MONTHLY_USD ?? 1_000_000);
const revenue = platform.revenueEngine.summary({ targetMonthlyUsd });
const growth = platform.growthEngine.summary();
const distribution = platform.revenueDistributionEngine.plan();
const proof = platform.proofService.reservesAndLiabilities();

const blockers = [];
if (!config.distribution.cryptoWallet) blockers.push("REVENUE_CRYPTO_WALLET missing");
for (const destination of config.distribution.fiatDestinations) {
  if (!destination.name) blockers.push(`Beneficiary name missing for ${destination.iban}`);
}
if (!config.distribution.fiatDestinations.length) blockers.push("Revenue fiat IBAN destinations missing");

const result = {
  status: blockers.length ? "ready_with_distribution_blockers" : "ready",
  targetMonthlyUsd,
  revenueTarget: revenue.requiredMonthlyVolume,
  growthCampaigns: growth.campaigns.map((campaign) => ({
    id: campaign.id,
    dailyTarget: campaign.dailyTarget,
    channel: campaign.channel
  })),
  distribution: {
    status: distribution.status,
    blockers: distribution.blockers
  },
  kubernetesScaleProfile: {
    minReplicas: 5,
    maxReplicas: 100,
    cpuTargetUtilization: 50,
    expectedUse: "front-door API, growth landing, wallet auth and read-heavy proof/revenue endpoints"
  },
  proof: {
    reserveRoot: proof.reserveRoot,
    liabilityRoot: proof.liabilityRoot,
    ledgerHash: platform.ledger.lastHash
  },
  blockers,
  createdAt: new Date().toISOString()
};

writeFileSync(OUTPUT, JSON.stringify(result, null, 2));
console.log(JSON.stringify({
  status: result.status,
  dailyVolumeTargetUsd: result.revenueTarget.dailyVolumeUsd,
  distributionStatus: result.distribution.status,
  blockers,
  output: OUTPUT
}, null, 2));

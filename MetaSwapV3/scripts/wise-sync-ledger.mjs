import { writeFileSync } from "node:fs";
import { loadEnvFile } from "../src/env-file.js";
import { loadConfig } from "../src/config.js";
import { createPlatform } from "../src/platform.js";
import { WiseClient } from "../src/adapters/wise-client.js";

const ENV_PATH = process.env.ENV_PATH ?? ".env.production";
const OUTPUT = ".data/wise-ledger-sync.json";
const ASSET = process.env.WISE_SYNC_ASSET ?? "EUR";

loadEnvFile(ENV_PATH);
const config = loadConfig();
const wise = new WiseClient(config.wise);
if (!wise.configured()) throw new Error("Wise is not configured");

const platform = createPlatform({ config });
const liveAvailable = round(await wise.availableBalance(ASSET));
const wiseAccount = platform.ledger.ensureAccount("platform", "bank", ASSET, "wise");
const currentLedgerAvailable = round(platform.ledger.balance(wiseAccount).available);
const delta = round(liveAvailable - currentLedgerAvailable);

let entry = null;
let action = "already_matched";

if (delta > 0) {
  const treasury = platform.ledger.ensureAccount("platform", "treasury", ASSET);
  const treasuryAvailable = platform.ledger.balance(treasury).available;
  if (treasuryAvailable >= delta) {
    entry = platform.ledger.postTransfer({
      from: treasury,
      to: wiseAccount,
      asset: ASSET,
      amount: delta,
      memo: `wise ledger sync increase profile ${config.wise.profileId} balance ${config.wise.balanceId}`
    });
    action = "treasury_to_wise_bank";
  } else {
    const external = platform.ledger.ensureAccount("external", `wise-statement:${config.wise.balanceId ?? config.wise.profileId}`, ASSET);
    platform.ledger.credit(external, "available", delta);
    entry = platform.ledger.postTransfer({
      from: external,
      to: wiseAccount,
      asset: ASSET,
      amount: delta,
      memo: `wise ledger sync external increase profile ${config.wise.profileId} balance ${config.wise.balanceId}`
    });
    action = "external_statement_to_wise_bank";
  }
} else if (delta < 0) {
  const suspense = platform.ledger.ensureAccount("platform", "suspense", ASSET, "wise-reconciliation");
  entry = platform.ledger.postTransfer({
    from: wiseAccount,
    to: suspense,
    asset: ASSET,
    amount: Math.abs(delta),
    memo: `wise ledger sync decrease profile ${config.wise.profileId} balance ${config.wise.balanceId}`
  });
  action = "wise_bank_to_suspense";
}

const finalLedgerAvailable = round(platform.ledger.balance(wiseAccount).available);
const proof = platform.proofService.reservesAndLiabilities();
const result = {
  status: finalLedgerAvailable === liveAvailable ? "matched" : "exception",
  provider: "wise",
  profileId: config.wise.profileId,
  balanceId: config.wise.balanceId,
  asset: ASSET,
  liveAvailable,
  ledgerAccount: wiseAccount,
  ledgerAvailableBefore: currentLedgerAvailable,
  ledgerAvailableAfter: finalLedgerAvailable,
  deltaApplied: delta,
  action,
  journalEntryId: entry?.id ?? null,
  ledgerHash: platform.ledger.lastHash,
  reserveRoot: proof.reserveRoot,
  liabilityRoot: proof.liabilityRoot,
  createdAt: new Date().toISOString()
};

platform.eventBus.publish("WiseLedgerSynchronized", result);
writeFileSync(OUTPUT, JSON.stringify(result, null, 2));
console.log(JSON.stringify({
  status: result.status,
  asset: result.asset,
  liveAvailable: result.liveAvailable,
  ledgerAvailableBefore: result.ledgerAvailableBefore,
  ledgerAvailableAfter: result.ledgerAvailableAfter,
  deltaApplied: result.deltaApplied,
  action: result.action,
  journalEntryId: result.journalEntryId,
  ledgerHash: result.ledgerHash,
  reserveRoot: result.reserveRoot,
  output: OUTPUT
}, null, 2));

function round(value) {
  return Math.round((Number(value) + Number.EPSILON) * 1e8) / 1e8;
}

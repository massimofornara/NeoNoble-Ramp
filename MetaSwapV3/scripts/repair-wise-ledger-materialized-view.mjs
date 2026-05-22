import { readFileSync, writeFileSync } from "node:fs";
import { loadEnvFile } from "../src/env-file.js";
import { loadConfig } from "../src/config.js";
import { createPlatform } from "../src/platform.js";

const ENV_PATH = process.env.ENV_PATH ?? ".env.production";
const SYNC_PATH = ".data/wise-ledger-sync.json";
const OUTPUT = ".data/wise-ledger-materialized-repair.json";

loadEnvFile(ENV_PATH);
const platform = createPlatform({ config: loadConfig() });
const sync = JSON.parse(readFileSync(SYNC_PATH, "utf8"));
if (!sync.journalEntryId) {
  writeFileSync(OUTPUT, JSON.stringify({ status: "not_required", reason: "No Wise sync journal entry" }, null, 2));
  console.log(JSON.stringify({ status: "not_required", output: OUTPUT }, null, 2));
  process.exit(0);
}

const entry = platform.ledger.journal.find((row) => row.id === sync.journalEntryId);
if (!entry) throw new Error(`Journal entry not found: ${sync.journalEntryId}`);

const repaired = [];
for (const posting of entry.postings) {
  const account = platform.ledger.accounts.get(posting.accountId);
  if (!account || account.ownerType !== "platform") continue;
  const expectedAvailable = expectedFromJournal(platform.ledger, posting.accountId);
  const balance = platform.ledger.balance(posting.accountId);
  const before = round(balance.available);
  const after = round(expectedAvailable);
  if (before !== after) {
    balance.available = after;
    balance.version += 1;
    platform.ledger.balances.set(posting.accountId, balance);
    platform.ledger.store?.saveAccount(account, balance);
    repaired.push({ accountId: posting.accountId, before, after });
  }
}

const proof = platform.proofService.reservesAndLiabilities();
const result = {
  status: repaired.length ? "repaired" : "already_consistent",
  sourceJournalEntryId: sync.journalEntryId,
  repaired,
  ledgerHash: platform.ledger.lastHash,
  reserveRoot: proof.reserveRoot,
  liabilityRoot: proof.liabilityRoot,
  createdAt: new Date().toISOString()
};

platform.eventBus.publish("LedgerMaterializedViewRepaired", result);
writeFileSync(OUTPUT, JSON.stringify(result, null, 2));
console.log(JSON.stringify({
  status: result.status,
  repaired: result.repaired,
  ledgerHash: result.ledgerHash,
  reserveRoot: result.reserveRoot,
  output: OUTPUT
}, null, 2));

function expectedFromJournal(ledger, accountId) {
  let value = 0;
  for (const row of ledger.journal) {
    for (const posting of row.postings ?? []) {
      if (posting.accountId !== accountId) continue;
      value += posting.side === "debit" ? Number(posting.amount) : -Number(posting.amount);
    }
  }
  return Math.max(0, round(value));
}

function round(value) {
  return Math.round((Number(value) + Number.EPSILON) * 1e8) / 1e8;
}

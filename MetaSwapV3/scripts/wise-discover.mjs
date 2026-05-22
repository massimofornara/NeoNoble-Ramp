import { readFileSync, writeFileSync } from "node:fs";
import { loadEnvFile } from "../src/env-file.js";
import { loadConfig } from "../src/config.js";

loadEnvFile(process.env.ENV_PATH ?? ".env.production");
const config = loadConfig();
if (!config.wise.baseUrl || !config.wise.accessToken) {
  throw new Error("WISE_BASE_URL and WISE_ACCESS_TOKEN are required");
}

const profiles = await wise("GET", "/v1/profiles");
const sanitizedProfiles = profiles.map((profile) => ({
  id: profile.id,
  type: profile.type,
  businessNameMatch: JSON.stringify(profile).toLowerCase().includes("neonoble"),
  displayNameHint: profile.displayName ? `${profile.displayName.slice(0, 3)}***` : undefined
}));
const selected = profiles.find((profile) => JSON.stringify(profile).toLowerCase().includes("neonoble"))
  ?? profiles.find((profile) => profile.type === "business")
  ?? profiles[0];

let balances = [];
if (selected?.id) {
  try {
    balances = await wise("GET", `/v4/profiles/${selected.id}/balances?types=STANDARD`);
  } catch {
    balances = [];
  }
}
const eurBalance = balances.find((balance) => balance.currency === "EUR");
const report = {
  discoveredAt: new Date().toISOString(),
  profileCount: profiles.length,
  profiles: sanitizedProfiles,
  selectedProfileId: selected?.id,
  selectedProfileType: selected?.type,
  eurBalanceId: eurBalance?.id,
  eurBalanceAvailable: eurBalance?.amount?.value ?? eurBalance?.availableAmount?.value ?? undefined
};
writeFileSync(".data/wise-discovery.json", JSON.stringify(report, null, 2));

if (selected?.id) updateEnv("WISE_PROFILE_ID", String(selected.id));
if (eurBalance?.id) updateEnv("WISE_BALANCE_ID", String(eurBalance.id));

console.log(JSON.stringify({
  profileCount: report.profileCount,
  selectedProfileId: report.selectedProfileId,
  selectedProfileType: report.selectedProfileType,
  eurBalanceFound: Boolean(report.eurBalanceId),
  output: ".data/wise-discovery.json"
}, null, 2));

async function wise(method, path) {
  const response = await fetch(new URL(path, config.wise.baseUrl), {
    method,
    headers: {
      authorization: `Bearer ${config.wise.accessToken}`,
      "content-type": "application/json"
    }
  });
  const text = await response.text();
  const parsed = text ? JSON.parse(text) : {};
  if (!response.ok) throw new Error(`wise ${response.status}: ${text}`);
  return parsed;
}

function updateEnv(key, value) {
  const path = process.env.ENV_PATH ?? ".env.production";
  let env = readFileSync(path, "utf8");
  const line = `${key}=${value}`;
  if (new RegExp(`^${key}=.*$`, "m").test(env)) env = env.replace(new RegExp(`^${key}=.*$`, "m"), line);
  else env += `${env.endsWith("\n") ? "" : "\n"}${line}\n`;
  writeFileSync(path, env);
}

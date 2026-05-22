import { loadEnvFile } from "../src/env-file.js";
import { loadConfig } from "../src/config.js";
import { WiseClient } from "../src/adapters/wise-client.js";

loadEnvFile(process.env.ENV_PATH ?? ".env.production");

const config = loadConfig();
const wise = new WiseClient(config.wise);
const status = wise.status();
const required = [
  ["WISE_BASE_URL", Boolean(config.wise.baseUrl)],
  ["WISE_ACCESS_TOKEN", Boolean(config.wise.accessToken)],
  ["WISE_PROFILE_ID", Boolean(config.wise.profileId)]
];
if (status.mtlsRequired) {
  required.push(["WISE_CLIENT_CERT_PATH", status.clientCertificate]);
  required.push(["WISE_CLIENT_KEY_PATH", status.clientPrivateKey]);
}
const missing = required.filter(([, ok]) => !ok).map(([key]) => key);

console.log(JSON.stringify({
  wiseProductionReady: wise.configured(),
  status,
  missing
}, null, 2));

if (missing.length) process.exitCode = 1;

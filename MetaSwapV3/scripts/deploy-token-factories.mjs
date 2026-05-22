import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";

const require = createRequire(import.meta.url);
const { ethers } = require("ethers");
let solc;
try {
  solc = require("solc");
} catch {
  solc = undefined;
}
const ENV_PATH = process.env.ENV_PATH ?? ".env.production";
const EVM_CHAINS = [
  ["ETHEREUM", "Ethereum"],
  ["BNB", "BNB Chain"],
  ["BASE", "Base"],
  ["POLYGON", "Polygon"]
];
const SOLANA_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA";

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log([
    "Usage: npm run deploy:token-factories",
    "Deploys missing EVM token factories and writes *_TOKEN_FACTORY_ADDRESS values to .env.production.",
    "Existing addresses are preserved. Set FORCE_TOKEN_FACTORY_DEPLOY=true to redeploy intentionally."
  ].join("\n"));
  process.exit(0);
}

const env = readEnv(ENV_PATH);
const forceDeploy = process.env.FORCE_TOKEN_FACTORY_DEPLOY === "true";
const needsEvmDeployment = EVM_CHAINS.some(([prefix]) => forceDeploy || !env[`${prefix}_TOKEN_FACTORY_ADDRESS`]);
const privateKey = needsEvmDeployment
  ? normalizePrivateKey(env.DEPLOYER_PRIVATE_KEY ?? process.env.DEPLOYER_PRIVATE_KEY)
  : "";
if (needsEvmDeployment && !privateKey) {
  throw new Error("DEPLOYER_PRIVATE_KEY is required to deploy EVM token factories on mainnet");
}

const artifact = needsEvmDeployment ? compileFactory() : undefined;
const deployed = {};

for (const [prefix, label] of EVM_CHAINS) {
  const existingAddress = env[`${prefix}_TOKEN_FACTORY_ADDRESS`];
  if (existingAddress && !forceDeploy) {
    deployed[prefix] = existingAddress;
    continue;
  }
  const urls = splitUrls(env[`${prefix}_RPC_URLS`] ?? env[`${prefix}_RPC_URL`]);
  if (!urls.length) throw new Error(`${prefix}_RPC_URLS is required`);
  const provider = new ethers.JsonRpcProvider(urls[0], Number(env[`${prefix}_CHAIN_ID`]));
  const wallet = new ethers.Wallet(privateKey, provider);
  const balance = await provider.getBalance(wallet.address);
  if (balance === 0n) throw new Error(`${label} deployer ${wallet.address} has zero native balance`);
  const factory = new ethers.ContractFactory(artifact.abi, artifact.bytecode, wallet);
  const contract = await factory.deploy(wallet.address);
  await contract.waitForDeployment();
  const address = await contract.getAddress();
  env[`${prefix}_TOKEN_FACTORY_ADDRESS`] = address;
  deployed[prefix] = address;
}

env.SOLANA_TOKEN_FACTORY_ADDRESS = env.SOLANA_TOKEN_FACTORY_ADDRESS || SOLANA_TOKEN_PROGRAM_ID;
writeEnv(ENV_PATH, env);

console.log(JSON.stringify({
  env: resolve(ENV_PATH),
  evmTokenFactories: deployed,
  solanaTokenProgram: env.SOLANA_TOKEN_FACTORY_ADDRESS
}, null, 2));

function compileFactory() {
  const source = readFileSync("contracts/evm/MetaSwapV3TokenFactory.sol", "utf8");
  const input = {
    language: "Solidity",
    sources: {
      "MetaSwapV3TokenFactory.sol": { content: source }
    },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": {
          MetaSwapV3TokenFactory: ["abi", "evm.bytecode.object"]
        }
      }
    }
  };
  const compilerOutput = solc
    ? solc.compile(JSON.stringify(input))
    : execFileSync(resolveSolcBinary(), ["--standard-json"], {
        input: JSON.stringify(input),
        encoding: "utf8",
        maxBuffer: 16 * 1024 * 1024
      });
  const output = JSON.parse(compilerOutput);
  const errors = (output.errors ?? []).filter((error) => error.severity === "error");
  if (errors.length) throw new Error(errors.map((error) => error.formattedMessage).join("\n"));
  const artifact = output.contracts["MetaSwapV3TokenFactory.sol"].MetaSwapV3TokenFactory;
  return { abi: artifact.abi, bytecode: `0x${artifact.evm.bytecode.object}` };
}

function readEnv(path) {
  const rows = readFileSync(path, "utf8").split(/\r?\n/);
  const map = {};
  for (const row of rows) {
    const line = row.trim();
    if (!line || line.startsWith("#")) continue;
    const index = line.indexOf("=");
    if (index < 1) continue;
    map[line.slice(0, index)] = normalizeEnvValue(line.slice(index + 1));
  }
  return map;
}

function writeEnv(path, map) {
  const content = Object.entries(map).map(([key, value]) => `${key}=${value}`).join("\n");
  writeFileSync(path, `${content}\n`);
}

function splitUrls(value = "") {
  return value.split(",").map((url) => url.trim()).filter(Boolean);
}

function normalizeEnvValue(value = "") {
  let normalized = value.trim();
  while (
    (normalized.startsWith('"') && normalized.endsWith('"')) ||
    (normalized.startsWith("'") && normalized.endsWith("'"))
  ) {
    normalized = normalized.slice(1, -1).trim();
  }
  return normalized;
}

function normalizePrivateKey(value = "") {
  const normalized = normalizeEnvValue(value);
  if (!normalized) return "";
  const key = normalized.startsWith("0x") ? normalized : `0x${normalized}`;
  if (!/^0x[0-9a-fA-F]{64}$/.test(key)) {
    throw new Error("DEPLOYER_PRIVATE_KEY has an invalid format; expected a 32-byte hex private key");
  }
  return key;
}

function resolveSolcBinary() {
  const candidates = [
    process.env.SOLC_PATH,
    "C:\\Users\\massi\\.solcx\\solc-v0.8.20\\solc.exe",
    "C:\\solc\\solc.exe.exe"
  ].filter(Boolean);
  const selected = candidates.find((candidate) => existsSync(candidate));
  if (!selected) throw new Error("solc package is not installed and no local solc binary was found");
  return selected;
}

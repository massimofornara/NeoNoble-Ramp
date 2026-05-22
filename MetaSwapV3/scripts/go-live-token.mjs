import { readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { ethers } = require("ethers");

const BASE_URL = process.env.BASE_URL ?? "http://127.0.0.1:8080";
const ENV_PATH = process.env.ENV_PATH ?? ".env.production";
const CHAIN = process.env.LIVE_TOKEN_CHAIN ?? "ethereum";
const DECIMALS = Number(process.env.LIVE_TOKEN_DECIMALS ?? 18);
const SUPPLY = BigInt(process.env.LIVE_TOKEN_SUPPLY ?? "1000000");
const EUR_PRICE = Number(process.env.LIVE_TOKEN_PRICE_EUR ?? 100);
const EUR_USD = Number(process.env.EUR_USD_RATE ?? 1.08);
const ISSUE_PRICE_USD = Number((EUR_PRICE * EUR_USD).toFixed(8));
const SYMBOL = process.env.LIVE_TOKEN_SYMBOL ?? `M100${Date.now().toString().slice(-5)}`;
const NAME = process.env.LIVE_TOKEN_NAME ?? `MetaSwapV3 ${EUR_PRICE} EUR Token ${SYMBOL}`;

const env = readEnv(ENV_PATH);
const privateKey = normalizePrivateKey(env.DEPLOYER_PRIVATE_KEY);
const wallet = new ethers.Wallet(privateKey);
const rpcUrls = splitUrls(env.ETHEREUM_RPC_URLS);
const factoryAddress = env.ETHEREUM_TOKEN_FACTORY_ADDRESS;
if (CHAIN !== "ethereum") throw new Error("This go-live runner is currently configured for ethereum mainnet");
if (!factoryAddress) throw new Error("ETHEREUM_TOKEN_FACTORY_ADDRESS is required");

const provider = await firstHealthyProvider(rpcUrls);
const signer = wallet.connect(provider);
const network = await provider.getNetwork();
if (network.chainId !== 1n) throw new Error(`Expected Ethereum mainnet chainId 1, got ${network.chainId}`);

const factory = new ethers.Contract(factoryAddress, [
  "function owner() view returns (address)",
  "function deployToken(string name,string symbol,uint256 supply,uint8 decimals,address tokenOwner) returns (address)",
  "event TokenDeployed(bytes32 indexed salt,address indexed token,address indexed tokenOwner,string name,string symbol,uint8 decimals,uint256 supply)"
], signer);

const owner = await factory.owner();
if (owner.toLowerCase() !== wallet.address.toLowerCase()) {
  throw new Error(`Factory owner ${owner} does not match deployer wallet ${wallet.address}`);
}

await api("POST", "/users", {
  id: "user-eu-1",
  name: "MetaSwap Production User",
  kycTier: "enhanced",
  jurisdiction: "EU",
  sanctionsClear: true,
  pep: false,
  fraudScore: 0.05,
  clusterId: "cluster-user-eu-1"
});
await api("POST", "/users", {
  id: "issuer-1",
  name: "MetaSwap Production Issuer",
  kycTier: "institutional",
  jurisdiction: "EU",
  sanctionsClear: true,
  pep: false,
  fraudScore: 0.02,
  clusterId: "cluster-issuer-1"
});

const challenge = await api("POST", "/wallets/challenge", {
  userId: "user-eu-1",
  address: wallet.address,
  chain: CHAIN,
  walletType: "eip1193"
});
const signature = await wallet.signMessage(challenge.message);
const session = await api("POST", "/wallets/verify", {
  challengeId: challenge.id,
  signature
});

const supplyUnits = SUPPLY * 10n ** BigInt(DECIMALS);
const gas = await factory.deployToken.estimateGas(NAME, SYMBOL, supplyUnits, DECIMALS, wallet.address);
const balance = await provider.getBalance(wallet.address);
const fee = (await provider.getFeeData()).maxFeePerGas ?? (await provider.getFeeData()).gasPrice ?? 0n;
if (fee > 0n && balance < gas * fee) {
  throw new Error(`Insufficient ETH for deployment gas. Required at least ${ethers.formatEther(gas * fee)} ETH, available ${ethers.formatEther(balance)} ETH`);
}

const tx = await factory.deployToken(NAME, SYMBOL, supplyUnits, DECIMALS, wallet.address);
const receipt = await tx.wait(1);
const event = receipt.logs
  .map((log) => {
    try { return factory.interface.parseLog(log); } catch { return undefined; }
  })
  .find((parsed) => parsed?.name === "TokenDeployed");
if (!event) throw new Error("TokenDeployed event not found in deployment receipt");
const tokenAddress = event.args.token;

const asset = await api("POST", "/tokens", {
  issuerId: "issuer-1",
  symbol: SYMBOL,
  name: NAME,
  maxSupply: Number(SUPPLY),
  issuePriceUsd: ISSUE_PRICE_USD,
  chains: [CHAIN],
  contracts: { [CHAIN]: tokenAddress },
  micaClassification: "utility",
  riskTier: "low",
  decimals: DECIMALS
});

const token = new ethers.Contract(tokenAddress, [
  "function balanceOf(address owner) view returns (uint256)",
  "function name() view returns (string)",
  "function symbol() view returns (string)",
  "function totalSupply() view returns (uint256)"
], provider);
const onchainBalance = await token.balanceOf(wallet.address);
const portfolio = await api("GET", `/wallets/portfolio/user-eu-1`);
const settlement = await api("GET", "/settlement/status");
const reconciliation = await api("GET", "/reconciliation");
const proof = await api("GET", "/proof/reserves-liabilities");
const rpcStatus = await api("GET", "/rpc/status");
const providers = await api("GET", "/providers");
const tokenImport = await api("GET", `/wallets/token-import/${SYMBOL}/${CHAIN}`);

const result = {
  chain: CHAIN,
  walletAddress: wallet.address,
  tokenName: NAME,
  tokenSymbol: SYMBOL,
  tokenAddress,
  deploymentTransactionHash: receipt.hash,
  blockNumber: receipt.blockNumber,
  initialPrice: { amount: EUR_PRICE, asset: "EUR", issuePriceUsd: ISSUE_PRICE_USD },
  listing: { lifecycle: asset.lifecycle, status: asset.status, rfqEnabled: asset.lifecycle === "rfq" },
  walletSessionId: session.id,
  onchainTokenBalance: ethers.formatUnits(onchainBalance, DECIMALS),
  portfolio,
  settlement,
  reconciliation,
  proof,
  rpcStatus: rpcStatus[CHAIN],
  providers,
  tokenImport
};

writeFileSync(".data/go-live-token-result.json", JSON.stringify(result, null, 2));
console.log(JSON.stringify({
  chain: result.chain,
  tokenAddress: result.tokenAddress,
  deploymentTransactionHash: result.deploymentTransactionHash,
  blockNumber: result.blockNumber,
  tokenSymbol: result.tokenSymbol,
  initialPrice: result.initialPrice,
  listing: result.listing,
  walletSessionId: result.walletSessionId,
  onchainTokenBalance: result.onchainTokenBalance,
  portfolioPositions: result.portfolio.balances.length,
  settlementEntries: result.settlement.ledgerEntries,
  pendingSettlementCount: result.settlement.pending.length,
  reconciliationRows: result.reconciliation.length,
  proofReserveRoot: result.proof.reserveRoot,
  output: ".data/go-live-token-result.json"
}, null, 2));

async function api(method, path, body) {
  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined
  });
  const text = await response.text();
  const parsed = text ? JSON.parse(text) : {};
  if (!response.ok) throw new Error(`${method} ${path} failed: ${text}`);
  return parsed;
}

async function firstHealthyProvider(urls) {
  let lastError;
  for (const url of urls) {
    try {
      const provider = new ethers.JsonRpcProvider(url, 1);
      await provider.getBlockNumber();
      return provider;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError ?? new Error("No Ethereum RPC URL configured");
}

function readEnv(path) {
  const map = {};
  for (const row of readFileSync(path, "utf8").split(/\r?\n/)) {
    const line = row.trim();
    if (!line || line.startsWith("#")) continue;
    const index = line.indexOf("=");
    if (index < 1) continue;
    map[line.slice(0, index)] = normalizeEnvValue(line.slice(index + 1));
  }
  return map;
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
  const key = normalized.startsWith("0x") ? normalized : `0x${normalized}`;
  if (!/^0x[0-9a-fA-F]{64}$/.test(key)) throw new Error("DEPLOYER_PRIVATE_KEY has invalid format");
  return key;
}

function splitUrls(value = "") {
  return value.split(",").map((url) => url.trim()).filter(Boolean);
}

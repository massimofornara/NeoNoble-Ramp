import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { loadEnvFile } from "../src/env-file.js";
import { loadConfig } from "../src/config.js";
import { createPlatform } from "../src/platform.js";

const require = createRequire(import.meta.url);
const { ethers } = require("ethers");

const ENV_PATH = process.env.ENV_PATH ?? ".env.production";
const CHAIN = "ethereum";
const USER_ID = process.env.DEPOSIT_SYNC_USER_ID ?? "user-eu-1";
const SYMBOL = process.env.DEPOSIT_SYNC_SYMBOL ?? "M10037205";
const TOKEN_ADDRESS = process.env.DEPOSIT_SYNC_TOKEN_ADDRESS ?? "0x64B08c0C4641651DBcA64E60CbC73968c65C60C4";
const DECIMALS = Number(process.env.DEPOSIT_SYNC_DECIMALS ?? 18);
const AMOUNT = process.env.DEPOSIT_SYNC_AMOUNT ?? "1000";
const OUTPUT = ".data/m10037205-real-deposit-sync.json";

loadEnvFile(ENV_PATH);
const config = loadConfig();
const deployer = new ethers.Wallet(normalizePrivateKey(process.env.DEPLOYER_PRIVATE_KEY));
const custody = ensureCustodyWallet(ENV_PATH);
const source = deployer;
const rpc = rawRpcClient(config.blockchain.ethereum.rpcUrls);
const chainId = Number(BigInt(await rpc("eth_chainId", [])));
if (chainId !== 1) throw new Error(`Expected Ethereum mainnet chainId 1, got ${chainId}`);

const units = ethers.parseUnits(AMOUNT, DECIMALS);
const [sourceBalanceBefore, custodyBalanceBefore, ethBalance] = await Promise.all([
  erc20Balance(rpc, TOKEN_ADDRESS, source.address),
  erc20Balance(rpc, TOKEN_ADDRESS, custody.address),
  rpc("eth_getBalance", [source.address, "latest"]).then(BigInt)
]);
if (sourceBalanceBefore < units) {
  throw new Error(`Insufficient ${SYMBOL} on source wallet`);
}

const data = encodeErc20Transfer(custody.address, units);
const gas = BigInt(await rpc("eth_estimateGas", [{ from: source.address, to: TOKEN_ADDRESS, value: "0x0", data }]));
const gasPrice = BigInt(await rpc("eth_gasPrice", [])) * 12n / 10n;
if (gasPrice > 0n && ethBalance < gas * gasPrice) {
  throw new Error(`Insufficient ETH for gas. Required at least ${ethers.formatEther(gas * gasPrice)} ETH, available ${ethers.formatEther(ethBalance)} ETH`);
}

const nonce = Number(BigInt(await rpc("eth_getTransactionCount", [source.address, "pending"])));
const signed = await source.signTransaction({
  chainId: 1,
  type: 0,
  nonce,
  to: TOKEN_ADDRESS,
  data,
  value: 0n,
  gasLimit: gas * 12n / 10n,
  gasPrice
});
const hash = await rpc("eth_sendRawTransaction", [signed]);
const receipt = await waitForReceipt(rpc, hash);
if (BigInt(receipt.status) !== 1n) throw new Error(`Token transfer failed: ${receipt.transactionHash}`);

const custodyBalanceAfter = await erc20Balance(rpc, TOKEN_ADDRESS, custody.address);
const platform = createPlatform({ config: loadConfig() });
const sync = await platform.blockchainEventListener.syncDeposits({
  userId: USER_ID,
  chain: CHAIN,
  custodyAddress: custody.address,
  tokenAddress: TOKEN_ADDRESS,
  symbol: SYMBOL,
  decimals: DECIMALS,
  fromBlock: ethers.toQuantity(receipt.blockNumber),
  toBlock: ethers.toQuantity(receipt.blockNumber)
});
const proof = platform.proofService.reservesAndLiabilities();
const balances = platform.ledger.balancesForOwner(USER_ID).filter((row) => row.asset === SYMBOL || row.asset === "EUR" || row.asset === "ETH");

const result = {
  status: "confirmed_and_synced",
  chain: CHAIN,
  userId: USER_ID,
  symbol: SYMBOL,
  tokenAddress: TOKEN_ADDRESS,
  sourceAddress: source.address,
  custodyAddress: custody.address,
  amount: Number(AMOUNT),
  transferTransactionHash: receipt.transactionHash,
  blockNumber: Number(BigInt(receipt.blockNumber)),
  sourceBalanceBefore: ethers.formatUnits(sourceBalanceBefore, DECIMALS),
  custodyBalanceBefore: ethers.formatUnits(custodyBalanceBefore, DECIMALS),
  custodyBalanceAfter: ethers.formatUnits(custodyBalanceAfter, DECIMALS),
  ledgerSync: sync,
  userBalances: balances,
  ledgerProof: {
    reserveRoot: proof.reserveRoot,
    liabilityRoot: proof.liabilityRoot,
    ledgerHash: platform.ledger.lastHash,
    journalEntries: platform.ledger.journal.length
  },
  completedAt: new Date().toISOString()
};

writeFileSync(OUTPUT, JSON.stringify(result, null, 2));
console.log(JSON.stringify({
  status: result.status,
  chain: result.chain,
  symbol: result.symbol,
  tokenAddress: result.tokenAddress,
  custodyAddress: result.custodyAddress,
  amount: result.amount,
  transferTransactionHash: result.transferTransactionHash,
  blockNumber: result.blockNumber,
  creditedAmount: result.ledgerSync.creditedAmount,
  ledgerHash: result.ledgerProof.ledgerHash,
  output: OUTPUT
}, null, 2));

function ensureCustodyWallet(path) {
  const existingKey = process.env.PLATFORM_ETHEREUM_CUSTODY_PRIVATE_KEY;
  if (existingKey) {
    const wallet = new ethers.Wallet(normalizePrivateKey(existingKey));
    process.env.PLATFORM_ETHEREUM_CUSTODY_ADDRESS = wallet.address;
    return wallet;
  }
  const wallet = ethers.Wallet.createRandom();
  const current = existsSync(path) ? readFileSync(path, "utf8") : "";
  const suffix = [
    "",
    "PLATFORM_ETHEREUM_CUSTODY_PRIVATE_KEY=<redacted-runtime-generated>",
    `PLATFORM_ETHEREUM_CUSTODY_ADDRESS=${wallet.address}`
  ].join("\n");
  writeFileSync(path, `${current.trimEnd()}\n${suffix.replace("<redacted-runtime-generated>", wallet.privateKey)}\n`);
  process.env.PLATFORM_ETHEREUM_CUSTODY_PRIVATE_KEY = wallet.privateKey;
  process.env.PLATFORM_ETHEREUM_CUSTODY_ADDRESS = wallet.address;
  return wallet;
}

function rawRpcClient(urls) {
  const rpcUrls = urls.filter(Boolean);
  if (!rpcUrls.length) throw new Error("No Ethereum RPC URL configured");
  let cursor = 0;
  return async function rpc(method, params) {
    let lastError;
    for (let attempt = 0; attempt < rpcUrls.length * 3; attempt += 1) {
      const url = rpcUrls[cursor % rpcUrls.length];
      cursor += 1;
      try {
        const response = await fetch(url, {
          method: "POST",
          signal: AbortSignal.timeout(45000),
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ jsonrpc: "2.0", id: Date.now(), method, params })
        });
        const payload = await response.json();
        if (payload.error) throw new Error(payload.error.message);
        return payload.result;
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError;
  };
}

async function erc20Balance(rpc, tokenAddress, ownerAddress) {
  const owner = ownerAddress.toLowerCase().replace("0x", "").padStart(64, "0");
  const raw = await rpc("eth_call", [{ to: tokenAddress, data: `0x70a08231${owner}` }, "latest"]);
  return BigInt(raw && raw !== "0x" ? raw : "0x0");
}

function encodeErc20Transfer(to, amount) {
  const address = to.toLowerCase().replace("0x", "").padStart(64, "0");
  const value = amount.toString(16).padStart(64, "0");
  return `0xa9059cbb${address}${value}`;
}

async function waitForReceipt(rpc, hash) {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    const receipt = await rpc("eth_getTransactionReceipt", [hash]);
    if (receipt) return receipt;
    await new Promise((resolve) => setTimeout(resolve, 4000));
  }
  throw new Error(`Timed out waiting for receipt ${hash}`);
}

function normalizePrivateKey(value = "") {
  const normalized = value.trim().replace(/^['"]|['"]$/g, "");
  const key = normalized.startsWith("0x") ? normalized : `0x${normalized}`;
  if (!/^0x[0-9a-fA-F]{64}$/.test(key)) throw new Error("Private key has invalid format");
  return key;
}

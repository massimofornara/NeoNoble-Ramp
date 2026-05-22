import { readFileSync, writeFileSync } from "node:fs";
import { loadEnvFile } from "../src/env-file.js";
import { loadConfig } from "../src/config.js";
import { createPlatform } from "../src/platform.js";
import { WiseClient } from "../src/adapters/wise-client.js";

const ENV_PATH = process.env.ENV_PATH ?? ".env.production";
const OUTPUT = ".data/end-to-end-core-flow.json";
const USER_ID = "user-eu-1";
const SYMBOL = "M10037205";
const TOKEN_ADDRESS = "0x64B08c0C4641651DBcA64E60CbC73968c65C60C4";
const USER_WALLET = "0xD436E1FbDFFD0a538D0A44A93c0dD52f92221862";

loadEnvFile(ENV_PATH);
const config = loadConfig();
const platform = createPlatform({ config });
const wise = new WiseClient(config.wise);
const deposit10k = JSON.parse(readFileSync(".data/m10037205-real-deposit-sync.json", "utf8"));
const deposit1k = JSON.parse(readFileSync(".data/m10037205-real-deposit-sync-1000-archive.json", "utf8"));

const custodyAddress = process.env.PLATFORM_ETHEREUM_CUSTODY_ADDRESS;
const rpc = rawRpcClient(config.blockchain.ethereum.rpcUrls);
const [userTokenRaw, custodyTokenRaw, userEthRaw, custodyEthRaw, blockRaw] = await Promise.all([
  erc20Balance(rpc, TOKEN_ADDRESS, USER_WALLET),
  erc20Balance(rpc, TOKEN_ADDRESS, custodyAddress),
  rpc("eth_getBalance", [USER_WALLET, "latest"]).then(BigInt),
  rpc("eth_getBalance", [custodyAddress, "latest"]).then(BigInt),
  rpc("eth_blockNumber", []).then(BigInt)
]);

const user = platform.complianceHub.getUser(USER_ID);
const userRisk = platform.complianceHub.scoreAml({ user, amountUsd: 0 });
const fairUsd = platform.pricingEngine.fairPriceUsd(SYMBOL);
const fairEur = platform.pricingEngine.midPrice(SYMBOL, "EUR");
const fairEth = platform.pricingEngine.midPrice(SYMBOL, "ETH");
const quoteEth = await platform.rfqEngine.requestQuote({ userRisk, symbol: SYMBOL, quoteAsset: "ETH", side: "sell", amount: 1000 });
const quoteEur = await platform.rfqEngine.requestQuote({ userRisk, symbol: SYMBOL, quoteAsset: "EUR", side: "sell", amount: 10000 });
const ethRequired = round(quoteEth.price * 1000);
const eurRequired = round(quoteEur.price * 10000);
const custodyEth = Number(custodyEthRaw) / 1e18;
const wiseAvailable = wise.configured() ? round(await wise.availableBalance("EUR")) : 0;
const balances = platform.ledger.balancesForOwner(USER_ID).filter((row) => ["M10037205", "ETH", "EUR"].includes(row.asset));
const exposureBefore = platform.treasuryService.exposure(SYMBOL);
const reconciliation = platform.reconciliationEngine.run();
const proof = platform.proofService.reservesAndLiabilities();
const portfolio = await safePortfolio(platform, USER_ID);

const blockers = [];
if (custodyEth < ethRequired) {
  blockers.push({
    code: "INSUFFICIENT_ONCHAIN_ETH_CUSTODY_RESERVE",
    requiredEth: ethRequired,
    availableEth: custodyEth,
    effect: "token_to_eth_broadcast_not_executed"
  });
}
if (wiseAvailable < eurRequired) {
  blockers.push({
    code: "INSUFFICIENT_WISE_EUR_AVAILABLE",
    requiredEur: eurRequired,
    availableEur: wiseAvailable,
    effect: "external_fiat_payout_not_executed"
  });
}

const result = {
  status: blockers.length ? "blocked_before_final_settlement" : "ready_for_final_settlement",
  chain: "ethereum",
  token: {
    symbol: SYMBOL,
    address: TOKEN_ADDRESS,
    unitPriceEurTarget: 100,
    fairPriceUsd: fairUsd,
    fairPriceEur: fairEur,
    fairPriceEth: fairEth
  },
  confirmedOnChainTransfers: {
    initialCustodyDeposit1000: {
      txHash: deposit1k.transferTransactionHash,
      blockNumber: deposit1k.blockNumber,
      amount: deposit1k.amount,
      ledgerCreditedAmount: deposit1k.ledgerSync?.creditedAmount
    },
    treasuryCustodyDeposit10000: {
      txHash: deposit10k.transferTransactionHash,
      blockNumber: deposit10k.blockNumber,
      amount: deposit10k.amount,
      ledgerCreditedAmount: deposit10k.ledgerSync?.creditedAmount
    }
  },
  rfq: {
    tokenToEth1000: {
      provider: quoteEth.provider,
      fairPrice: fairEth,
      executionPrice: quoteEth.price,
      spread: quoteEth.spread,
      quoteAmountEth: ethRequired,
      confidence: quoteEth.confidence,
      ttlMs: quoteEth.ttlMs,
      hedgeStatus: "not_routed_insufficient_onchain_custody_reserve"
    },
    tokenToFiat10000: {
      provider: quoteEur.provider,
      fairPrice: fairEur,
      executionPrice: quoteEur.price,
      spread: quoteEur.spread,
      quoteAmountEur: eurRequired,
      confidence: quoteEur.confidence,
      ttlMs: quoteEur.ttlMs,
      hedgeStatus: "not_routed_insufficient_wise_balance"
    }
  },
  inventoryMovementIfSettled: {
    tokenToEth1000: [
      { account: `customer:${USER_ID}:${SYMBOL}`, delta: -1000 },
      { account: `platform:inventory:${SYMBOL}`, delta: 1000 },
      { account: "platform:inventory:ETH", delta: -ethRequired },
      { account: `customer:${USER_ID}:ETH`, delta: ethRequired }
    ],
    tokenToFiat10000: [
      { account: `customer:${USER_ID}:${SYMBOL}`, delta: -10000 },
      { account: `platform:inventory:${SYMBOL}`, delta: 10000 },
      { account: "platform:treasury:EUR", delta: -eurRequired },
      { account: `customer:${USER_ID}:EUR`, delta: eurRequired }
    ]
  },
  onChainBalances: {
    blockNumber: Number(blockRaw),
    userWallet: USER_WALLET,
    custodyAddress,
    userToken: format18(userTokenRaw),
    custodyToken: format18(custodyTokenRaw),
    userEth: format18(userEthRaw),
    custodyEth: format18(custodyEthRaw)
  },
  ledger: {
    userBalances: balances,
    postingsExecutedInThisRun: [],
    note: "No trade settlement postings were executed because final ETH/Wise settlement conditions are not satisfied."
  },
  reconciliation,
  treasuryExposure: {
    before: exposureBefore,
    final: exposureBefore
  },
  proof: {
    reserveRoot: proof.reserveRoot,
    liabilityRoot: proof.liabilityRoot,
    ledgerHash: platform.ledger.lastHash
  },
  portfolio,
  externalFiat: {
    provider: "wise",
    availableEur: wiseAvailable,
    payoutReferences: [],
    status: wiseAvailable >= eurRequired ? "funds_available" : "blocked_insufficient_live_funds"
  },
  blockers,
  completedAt: new Date().toISOString()
};

platform.eventBus.publish("EndToEndCoreFlowEvaluated", result);
writeFileSync(OUTPUT, JSON.stringify(result, null, 2));
console.log(JSON.stringify({
  status: result.status,
  tokenToEthQuoteAmount: ethRequired,
  tokenToFiatQuoteAmount: eurRequired,
  custodyEth,
  wiseAvailable,
  blockers,
  deposit1000Tx: result.confirmedOnChainTransfers.initialCustodyDeposit1000.txHash,
  deposit10000Tx: result.confirmedOnChainTransfers.treasuryCustodyDeposit10000.txHash,
  reserveRoot: result.proof.reserveRoot,
  liabilityRoot: result.proof.liabilityRoot,
  output: OUTPUT
}, null, 2));

async function safePortfolio(platform, userId) {
  try {
    return await platform.portfolioEngine.portfolio(userId);
  } catch (error) {
    return { status: "unavailable", error: error.message };
  }
}

function rawRpcClient(urls) {
  const rpcUrls = urls.filter(Boolean);
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

function format18(value) {
  return (Number(value) / 1e18).toString();
}

function round(value) {
  return Math.round((Number(value) + Number.EPSILON) * 1e8) / 1e8;
}

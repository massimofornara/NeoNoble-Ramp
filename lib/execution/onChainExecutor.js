import { createRequire } from "node:module"

const require = createRequire(import.meta.url)
const { getChainAdapter } = require("../chains/adapters.cjs")
const { quoteFixedNenoToUsdt } = require("../cross-chain/pricingEngine.cjs")

function toNumber(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export async function getOnChainPreflight(transaction) {
  const chain = transaction.chainName || transaction.network || "BSC"
  const adapter = getChainAdapter(chain)
  const executionWallet = await adapter.getHotWalletAddress()
  const nativeBalance = await adapter.getNativeBalance(executionWallet)
  const nenoBalance = await adapter.getTokenBalance("NENO", executionWallet)
  const usdtBalance = await adapter.getTokenBalance("USDT", executionWallet)
  const quote =
    String(transaction.fromToken || "").toUpperCase() === "NENO" &&
    String(transaction.toToken || "").toUpperCase() === "USDT"
      ? quoteFixedNenoToUsdt(transaction.cryptoAmount || "0")
      : null

  const requiredUsdt = quote?.outputAmount || transaction.fiatAmount || "0"

  return {
    chain: {
      chainId: adapter.config.chainId,
      chainName: adapter.config.chainName,
      settlementLayer: adapter.config.settlementLayer,
    },
    executionWallet,
    balances: {
      native: nativeBalance,
      NENO: nenoBalance,
      USDT: usdtBalance,
    },
    quote,
    canExecuteSwapPayout: toNumber(usdtBalance) >= toNumber(requiredUsdt),
    hasOfframpTreasury: Boolean(process.env.OFFRAMP_TREASURY_ADDRESS || process.env.BURN_ADDRESS),
    mode: process.env.BLOCKCHAIN_EXECUTION_MODE || "disabled",
  }
}

export async function canUseOnChainExecutor(transaction) {
  const preflight = await getOnChainPreflight(transaction)
  const modeEnabled = preflight.mode === "real"

  if (transaction.type === "swap") {
    return {
      ok: modeEnabled && preflight.canExecuteSwapPayout,
      reason: !modeEnabled
        ? "BLOCKCHAIN_EXECUTION_MODE is not real"
        : preflight.canExecuteSwapPayout
          ? "on-chain liquidity available"
          : "insufficient USDT liquidity on execution wallet",
      preflight,
    }
  }

  if (transaction.type === "offramp") {
    return {
      ok: modeEnabled && preflight.hasOfframpTreasury,
      reason: !modeEnabled
        ? "BLOCKCHAIN_EXECUTION_MODE is not real"
        : preflight.hasOfframpTreasury
          ? "treasury lock/burn address configured"
          : "missing OFFRAMP_TREASURY_ADDRESS or BURN_ADDRESS",
      preflight,
    }
  }

  return {
    ok: false,
    reason: `transaction type ${transaction.type} is not executed on-chain by this router`,
    preflight,
  }
}

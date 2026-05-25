import { createRequire } from "node:module"
import { NextResponse } from "next/server"
import { getMoonPayConfig, getStripeRailConfig } from "@/lib/execution/providerConfig"

const require = createRequire(import.meta.url)
const { getChainAdapter } = require("../../../../lib/chains/adapters.cjs")
const { getTokenConfig } = require("../../../../lib/blockchain/tokenRegistry.cjs")
const { quoteFixedNenoToUsdt } = require("../../../../lib/cross-chain/pricingEngine.cjs")
const { buildLiquidityPlan, getProviderLiquidityState } = require("../../../../lib/liquidity/liquidityManager.cjs")
const { buildBootstrapPlan, buildUnifiedExecutionPool } = require("../../../../lib/liquidity/bootstrapLayer.cjs")

export async function POST(request) {
  try {
    const body = await request.json()
    const chain = body.chain || body.network || "BSC"
    const adapter = getChainAdapter(chain)
    const executionWallet = await adapter.getHotWalletAddress()
    const nativeBalance = await adapter.getNativeBalance(executionWallet)
    const nenoBalance = await adapter.getTokenBalance("NENO", executionWallet)
    const usdtBalance = await adapter.getTokenBalance("USDT", executionWallet)
    const quote = quoteFixedNenoToUsdt(body.amount || body.cryptoAmount || "0")
    const syntheticTransaction = {
      id: body.transactionId || "preflight",
      type: body.type || "swap",
      userId: body.userId || "preflight",
      fromToken: body.fromToken || "NENO",
      toToken: body.toToken || "USDT",
      cryptoAmount: body.amount || body.cryptoAmount || "0",
      fiatAmount: body.fiatAmount || quote.outputAmount,
      fiatCurrency: body.fiatCurrency || "EUR",
      network: chain,
      chainName: chain,
      toAddress: body.toAddress,
      paymentReference: body.paymentReference,
    }
    const liquidityState = await getProviderLiquidityState({ chain })
    const liquidityPlan = await buildLiquidityPlan(syntheticTransaction, { state: liquidityState })

    return NextResponse.json({
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
      tokenContracts: {
        NENO: getTokenConfig("NENO", chain),
        USDT: getTokenConfig("USDT", chain),
      },
      quote,
      canExecuteSwapPayout: Number(usdtBalance) >= Number(quote.outputAmount),
      hasFiatRail:
        Boolean(process.env.SEPA_PAYOUT_API_URL && process.env.SEPA_PROVIDER_API_KEY) ||
        Boolean(process.env.TRANSAK_PAYOUT_API_URL && process.env.TRANSAK_API_KEY) ||
        Boolean(process.env.STRIPE_SECRET_KEY),
      providerRails: {
        transakWidget: Boolean(process.env.NEXT_PUBLIC_TRANSAK_API_KEY && (process.env.TRANSAK_ACCESS_TOKEN || process.env.TRANSAK_API_SECRET)),
        moonpayWidget: Boolean(getMoonPayConfig().publishableKey),
        moonpaySignedUrls: Boolean(getMoonPayConfig().secretKey),
        stripe: {
          enabled: getStripeRailConfig().enabled,
          configured: Boolean(getStripeRailConfig().secretKey),
          payoutsEnabled: getStripeRailConfig().payoutsEnabled,
          fiatBackedSwapEnabled: getStripeRailConfig().fiatBackedSwapEnabled,
        },
      },
      hasOfframpTreasury: Boolean(process.env.OFFRAMP_TREASURY_ADDRESS || process.env.BURN_ADDRESS),
      mode: process.env.BLOCKCHAIN_EXECUTION_MODE || "disabled",
      liquidity: {
        canSettle: liquidityPlan.canSettle,
        required: liquidityPlan.required,
        selected: liquidityPlan.selected,
        blockers: liquidityPlan.blockers,
        providers: liquidityState.providers,
        executionPool: buildUnifiedExecutionPool(liquidityState),
        bootstrap: buildBootstrapPlan(syntheticTransaction, liquidityPlan),
      },
    })
  } catch (error) {
    return NextResponse.json({ error: error.message || "Execution preflight failed" }, { status: 400 })
  }
}

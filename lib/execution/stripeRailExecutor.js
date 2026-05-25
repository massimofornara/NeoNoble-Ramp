import Stripe from "stripe"
import { getStripeRailConfig } from "./providerConfig.js"

function requireStripe() {
  const config = getStripeRailConfig()
  if (!config.enabled) {
    throw new Error("Stripe rail fallback is disabled; set STRIPE_RAIL_ENABLED=true for provider-backed settlement")
  }
  if (!config.secretKey) {
    throw new Error("STRIPE_SECRET_KEY is required for Stripe rail fallback")
  }
  return {
    config,
    stripe: new Stripe(config.secretKey, {
      apiVersion: "2026-04-22.dahlia",
    }),
  }
}

function toMinorUnits(amount) {
  const [whole, fraction = ""] = String(amount || "0").split(".")
  return Number.parseInt(`${whole}${fraction.padEnd(2, "0").slice(0, 2)}`, 10)
}

async function getAvailableMinorUnits(stripe, currency, connectedAccountId) {
  const balance = await stripe.balance.retrieve(
    connectedAccountId ? { stripeAccount: connectedAccountId } : undefined,
  )
  return balance.available
    .filter((entry) => entry.currency === currency)
    .reduce((sum, entry) => sum + entry.amount, 0)
}

export async function createStripeSettlementAction(transaction) {
  const { config, stripe } = requireStripe()
  const currency = String(transaction.fiatCurrency || "eur").toLowerCase()

  if (transaction.type === "onramp") {
    const intent = await stripe.paymentIntents.create({
      amount: toMinorUnits(transaction.fiatAmount),
      currency,
      metadata: {
        transactionId: transaction.id,
        userId: transaction.userId,
        provider: "stripe",
      },
      automatic_payment_methods: {
        enabled: true,
      },
    })

    return {
      provider: "stripe",
      type: "payment_intent",
      settlementId: intent.id,
      clientSecret: intent.client_secret,
      status: intent.status,
    }
  }

  if (transaction.type === "offramp") {
    if (!config.payoutsEnabled) {
      throw new Error("Stripe payouts are disabled; set STRIPE_PAYOUTS_ENABLED=true and configure payout destination")
    }

    const amount = toMinorUnits(transaction.fiatAmount)
    const available = await getAvailableMinorUnits(stripe, currency, config.connectedAccountId)
    if (available < amount) {
      throw new Error(`Stripe ${currency.toUpperCase()} available balance is insufficient for payout`)
    }

    const payout = await stripe.payouts.create(
      {
        amount,
        currency,
        metadata: {
          transactionId: transaction.id,
          userId: transaction.userId,
          provider: "stripe",
        },
      },
      config.connectedAccountId ? { stripeAccount: config.connectedAccountId } : undefined,
    )

    return {
      provider: "stripe",
      type: "payout",
      settlementId: payout.id,
      status: payout.status,
    }
  }

  if (transaction.type === "swap" && config.fiatBackedSwapEnabled) {
    return {
      provider: "stripe",
      type: "fiat_backed_liquidity_bridge",
      status: "settlement_pending",
      reason:
        "Stripe fiat-backed bridge accepted for deferred liquidity reconciliation; USDT delivery still requires provider or treasury confirmation",
    }
  }

  throw new Error(`Stripe rail does not support ${transaction.type} without explicit configuration`)
}

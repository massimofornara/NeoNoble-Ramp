import { getAppOrigin, getMoonPayConfig, signMoonPayUrl } from "./providerConfig.js"

const SELL_FIAT_METHODS = new Set([
  "credit_debit_card",
  "ach_bank_transfer",
  "gbp_bank_transfer",
  "gbp_open_banking_payment",
  "sepa_bank_transfer",
  "paypal",
  "venmo",
  "moonpay_balance",
])

function normalizeMoonPayCurrency(asset) {
  const value = String(asset || "").trim().toLowerCase()
  if (value === "neno") return process.env.MOONPAY_NENO_CURRENCY_CODE || "neno"
  if (value === "usdt") return process.env.MOONPAY_USDT_CURRENCY_CODE || "usdt"
  if (value === "eur") return "eur"
  return value
}

function buildWidgetUrl(flow, params) {
  const config = getMoonPayConfig()
  const url = new URL(config.widgetBaseUrl)
  Object.entries({ apiKey: config.publishableKey, ...params }).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value))
    }
  })
  url.searchParams.set("flow", flow)
  return url.toString()
}

export function verifyMoonPayConfigured() {
  const config = getMoonPayConfig()
  if (!config.publishableKey) {
    throw new Error("NEXT_PUBLIC_MOONPAY_API_KEY or MOONPAY_API_KEY is required for MoonPay fallback")
  }
  return config
}

export function createMoonPayWidgetAction(transaction, options = {}) {
  const config = verifyMoonPayConfigured()
  const origin = getAppOrigin(options.origin)
  const flow = options.flow || (transaction.type === "swap" ? "swap" : "sell")
  const externalTransactionId = transaction.id
  const externalCustomerId = transaction.userId
  const redirectURL = `${origin}/exchange?provider=moonpay&transactionId=${encodeURIComponent(transaction.id)}`

  const params =
    flow === "sell"
      ? {
          baseCurrencyCode: normalizeMoonPayCurrency(transaction.fromToken || "NENO"),
          baseCurrencyAmount: transaction.cryptoAmount,
          defaultBaseCurrencyCode: normalizeMoonPayCurrency(transaction.fromToken || "NENO"),
          quoteCurrencyCode: normalizeMoonPayCurrency(transaction.fiatCurrency || "EUR"),
          lockAmount: "true",
          externalTransactionId,
          externalCustomerId,
          paymentMethod: SELL_FIAT_METHODS.has(String(options.paymentMethod || "").toLowerCase())
            ? String(options.paymentMethod).toLowerCase()
            : undefined,
          redirectURL,
        }
      : {
          baseCurrencyCode: normalizeMoonPayCurrency(transaction.fromToken || "NENO"),
          baseCurrencyAmount: transaction.cryptoAmount,
          quoteCurrencyCode: normalizeMoonPayCurrency(transaction.toToken || "USDT"),
          externalTransactionId,
          externalCustomerId,
          redirectURL,
        }

  const unsignedUrl = buildWidgetUrl(flow, params)
  const signature = config.secretKey ? signMoonPayUrl(unsignedUrl, config.secretKey) : null
  const signedUrl = signature ? `${unsignedUrl}&signature=${encodeURIComponent(signature)}` : unsignedUrl

  return {
    provider: "moonpay",
    type: "widget",
    flow,
    environment: config.environment,
    sdkUrl: config.sdkUrl,
    widgetUrl: signedUrl,
    signatureRequired: Boolean(config.secretKey),
    params,
    externalTransactionId,
    docs: {
      sdk: "https://dev.moonpay.com/widget/on-ramp-web-sdk",
      offRampParams: "https://dev.moonpay.com/widget/ramps-sdk-sell-params",
      urlSigning: "https://dev.moonpay.com/widget/on-ramp-enhance-security-using-signed-urls",
    },
  }
}

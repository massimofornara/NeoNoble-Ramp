import crypto from "node:crypto"

export function getAppOrigin(fallbackOrigin) {
  return (
    fallbackOrigin ||
    process.env.NEXT_PUBLIC_APP_URL ||
    process.env.APP_URL ||
    "http://localhost:3000"
  )
}

export function getMoonPayConfig() {
  const environment =
    String(process.env.MOONPAY_ENVIRONMENT || process.env.NEXT_PUBLIC_MOONPAY_ENVIRONMENT || "sandbox").toLowerCase() ===
    "production"
      ? "production"
      : "sandbox"

  return {
    environment,
    publishableKey: process.env.NEXT_PUBLIC_MOONPAY_API_KEY || process.env.MOONPAY_API_KEY || "",
    secretKey: process.env.MOONPAY_SECRET_KEY || "",
    webhookApiKey: process.env.MOONPAY_WEBHOOK_API_KEY || "",
    widgetBaseUrl: environment === "production" ? "https://buy.moonpay.com" : "https://buy-sandbox.moonpay.com",
    sdkUrl: "https://static.moonpay.com/web-sdk/v1/moonpay-web-sdk.min.js",
  }
}

export function signMoonPayUrl(url, secretKey) {
  if (!secretKey) {
    throw new Error("MOONPAY_SECRET_KEY is required to sign sensitive MoonPay widget URLs")
  }

  return crypto
    .createHmac("sha256", secretKey)
    .update(new URL(url).search)
    .digest("base64")
}

export function getStripeRailConfig() {
  return {
    enabled:
      process.env.STRIPE_RAIL_ENABLED === "true" ||
      process.env.STRIPE_SEPA_FALLBACK_ENABLED === "true" ||
      process.env.STRIPE_FIAT_BACKED_SWAP_ENABLED === "true",
    secretKey: process.env.STRIPE_SECRET_KEY || "",
    payoutsEnabled: process.env.STRIPE_PAYOUTS_ENABLED === "true",
    fiatBackedSwapEnabled: process.env.STRIPE_FIAT_BACKED_SWAP_ENABLED === "true",
    connectedAccountId: process.env.STRIPE_CONNECTED_ACCOUNT_ID || "",
  }
}

export function isProviderSettlementLayer(layer) {
  return ["transak", "moonpay", "stripe"].includes(String(layer || "").toLowerCase())
}

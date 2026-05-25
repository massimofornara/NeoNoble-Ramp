import { createWidgetSession } from "../transak/client.js"
import { getAppOrigin } from "./providerConfig.js"

function toNumberOrUndefined(value) {
  if (value === undefined || value === null || value === "") return undefined
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return undefined
  return parsed
}

export async function createTransakWidgetAction(transaction, options = {}) {
  const origin = getAppOrigin(options.origin)
  const productsAvailed = options.productsAvailed || (transaction.type === "onramp" ? "BUY" : "SELL")
  const session = await createWidgetSession(
    {
      productsAvailed,
      fiatCurrency: transaction.fiatCurrency || "EUR",
      cryptoCurrency: transaction.fromToken || transaction.toToken || "NENO",
      network: String(transaction.network || "bsc").toLowerCase(),
      cryptoAmount: toNumberOrUndefined(transaction.cryptoAmount),
      fiatAmount: transaction.type === "onramp" ? toNumberOrUndefined(transaction.fiatAmount) : undefined,
      paymentMethod: options.paymentMethod || "sepa_bank_transfer",
      walletRedirection: transaction.type === "offramp",
      partnerOrderId: transaction.id,
      partnerCustomerId: transaction.userId,
      redirectURL: `${origin}/exchange?provider=transak&transactionId=${encodeURIComponent(transaction.id)}`,
      exchangeScreenTitle: transaction.type === "offramp" ? "NeoNoble EUR off-ramp" : "NeoNoble NENO on-ramp",
      colorMode: "DARK",
      themeColor: "#00f5d4",
    },
    origin,
  )

  return {
    provider: "transak",
    type: "widget",
    flow: productsAvailed === "SELL" ? "sell" : "buy",
    widgetUrl: session.widgetUrl,
    partnerOrderId: session.partnerOrderId,
    partnerCustomerId: session.partnerCustomerId,
    docs: {
      session: "https://docs.transak.com/api/public/create-widget-url",
      sdk: "https://docs.transak.com/integration/web/js-sdk",
      params: "https://docs.transak.com/customization/query-parameters",
    },
  }
}

import { createRequire } from "node:module"
import { NextResponse } from "next/server"

const require = createRequire(import.meta.url)
const { planCrossChainSwap } = require("../../../../lib/cross-chain/bridgeRouter.cjs")

export async function GET(request) {
  try {
    const params = request.nextUrl.searchParams
    return NextResponse.json(
      planCrossChainSwap({
        fromChain: params.get("fromChain") || "BSC",
        toChain: params.get("toChain") || "BSC",
        fromAsset: params.get("fromAsset") || "NENO",
        toAsset: params.get("toAsset") || "USDT",
        amount: params.get("amount") || "1",
      }),
    )
  } catch (error) {
    return NextResponse.json({ error: error.message || "Unable to quote route" }, { status: 400 })
  }
}

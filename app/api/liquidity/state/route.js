import { createRequire } from "node:module"
import { NextResponse } from "next/server"

const require = createRequire(import.meta.url)
const { getProviderLiquidityState } = require("../../../../lib/liquidity/liquidityManager.cjs")
const { buildUnifiedExecutionPool } = require("../../../../lib/liquidity/bootstrapLayer.cjs")

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url)
    const chain = searchParams.get("chain") || "BSC"
    const state = await getProviderLiquidityState({ chain })
    return NextResponse.json({
      ...state,
      executionPool: buildUnifiedExecutionPool(state),
    })
  } catch (error) {
    return NextResponse.json({ error: error.message || "Liquidity state failed" }, { status: 400 })
  }
}

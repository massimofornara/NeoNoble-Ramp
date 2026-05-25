import { createRequire } from "node:module"
import { NextResponse } from "next/server"
import { prisma } from "@/lib/db"

const require = createRequire(import.meta.url)
const { buildLiquidityPlan } = require("../../../../lib/liquidity/liquidityManager.cjs")
const { buildBootstrapPlan } = require("../../../../lib/liquidity/bootstrapLayer.cjs")

export async function POST(request) {
  try {
    const body = await request.json()
    let transaction = body.transaction
    if (body.transactionId) {
      transaction = await prisma.transaction.findUnique({ where: { id: String(body.transactionId) } })
    }
    if (!transaction) {
      return NextResponse.json({ error: "transaction or transactionId is required" }, { status: 400 })
    }
    const plan = await buildLiquidityPlan(transaction)
    return NextResponse.json({
      ...plan,
      bootstrap: buildBootstrapPlan(transaction, plan),
    })
  } catch (error) {
    return NextResponse.json({ error: error.message || "Liquidity planning failed" }, { status: 400 })
  }
}

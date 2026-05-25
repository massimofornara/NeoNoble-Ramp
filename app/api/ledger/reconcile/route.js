import { NextResponse } from "next/server"
import { createRequire } from "node:module"
import { prisma } from "@/lib/db"
import { getUserLedgerReconciliation } from "@/lib/ledger/ledgerService"

const require = createRequire(import.meta.url)
const { reconcileUserTransactions } = require("../../../../lib/reconciliation/blockchainReconciler.cjs")

export async function GET(request) {
  const userId = request.nextUrl.searchParams.get("userId")
  if (!userId) {
    return NextResponse.json({ error: "userId is required" }, { status: 400 })
  }

  const syncChain = request.nextUrl.searchParams.get("syncChain") === "true"
  const chain = syncChain ? await reconcileUserTransactions(prisma, userId) : null
  const ledger = await getUserLedgerReconciliation(userId)

  return NextResponse.json({
    ...ledger,
    chain,
  })
}

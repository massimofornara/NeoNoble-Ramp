import { NextResponse } from "next/server"
import { prisma } from "@/lib/db"
import { routeExecution } from "@/lib/execution/executionRouter"

export async function POST(request) {
  try {
    const body = await request.json()
    if (!body.transactionId) {
      return NextResponse.json({ error: "transactionId is required" }, { status: 400 })
    }

    const transaction = await prisma.transaction.findUnique({ where: { id: String(body.transactionId) } })
    if (!transaction) {
      return NextResponse.json({ error: "Transaction not found" }, { status: 404 })
    }

    const routed = await routeExecution(transaction, {
      origin: request.headers.get("origin"),
      paymentMethod: body.paymentMethod,
    })

    return NextResponse.json({
      transactionId: routed.transaction.id,
      status: routed.transaction.status,
      step: routed.transaction.step,
      settlementLayer: routed.transaction.settlementLayer,
      executionRoute: routed.route,
    })
  } catch (error) {
    return NextResponse.json({ error: error.message || "Execution routing failed" }, { status: 400 })
  }
}

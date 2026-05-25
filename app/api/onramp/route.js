import { NextResponse } from "next/server"
import { createLedgerTransactionFromRequest } from "@/lib/ledger/ledgerService"
import { routeExecution } from "@/lib/execution/executionRouter"

export async function POST(request) {
  try {
    const body = await request.json()
    const transaction = await createLedgerTransactionFromRequest("onramp", {
      ...body,
      toToken: body.toToken || "NENO",
    })
    const routed = await routeExecution(transaction, {
      origin: request.headers.get("origin"),
      paymentMethod: body.paymentMethod,
    })

    return NextResponse.json(
      {
        success: true,
        type: "onramp",
        status: routed.transaction.status,
        transactionId: routed.transaction.id,
        currentStep: routed.transaction.step,
        settlementLayer: routed.transaction.settlementLayer,
        executionAttempts: routed.transaction.executionAttempts,
        fallbackPath: routed.transaction.fallbackPath,
        lastSuccessfulRail: routed.transaction.lastSuccessfulRail,
        executionRoute: routed.route,
        data: body,
      },
      { status: routed.transaction.status === "failed" ? 409 : 202 },
    )
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error.message || "Unable to create onramp transaction" },
      { status: 400 },
    )
  }
}

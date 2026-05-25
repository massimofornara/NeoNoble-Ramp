import { NextResponse } from "next/server"
import { createLedgerTransactionFromRequest } from "@/lib/ledger/ledgerService"
import { routeExecution } from "@/lib/execution/executionRouter"

export async function POST(request) {
  try {
    const body = await request.json()
    const transaction = await createLedgerTransactionFromRequest("offramp", {
      ...body,
      fromToken: body.fromToken || "NENO",
    })
    const routed = await routeExecution(transaction, {
      origin: request.headers.get("origin"),
      paymentMethod: body.paymentMethod || "sepa_bank_transfer",
    })

    return NextResponse.json(
      {
        success: true,
        type: "offramp",
        status: routed.transaction.status,
        transactionId: routed.transaction.id,
        txHash: routed.transaction.txHash,
        settlementId: routed.transaction.settlementId,
        currentStep: routed.transaction.step,
        chainStatus: routed.transaction.chainStatus,
        finalityStatus: routed.transaction.finalityStatus,
        settlementLayer: routed.transaction.settlementLayer,
        executionAttempts: routed.transaction.executionAttempts,
        fallbackPath: routed.transaction.fallbackPath,
        lastSuccessfulRail: routed.transaction.lastSuccessfulRail,
        estimatedCompletion: null,
        executionRoute: routed.route,
        data: body,
      },
      { status: routed.transaction.status === "failed" ? 409 : 202 },
    )
  } catch (error) {
    return NextResponse.json(
      { success: false, error: error.message || "Unable to create offramp transaction" },
      { status: 400 },
    )
  }
}

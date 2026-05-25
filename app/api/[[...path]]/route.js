import { NextResponse } from "next/server"
import { createLedgerTransactionFromRequest } from "@/lib/ledger/ledgerService"

function handleCORS(response) {
  response.headers.set("Access-Control-Allow-Origin", "*")
  response.headers.set("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
  response.headers.set("Access-Control-Allow-Headers", "Content-Type, Authorization")
  return response
}

async function handleRoute(request, { params }) {
  try {
    const method = request.method
    const path = params.path || []
    const route = "/" + path.join("/")

    // ROOT
    if ((route === "/" || route === "/root") && method === "GET") {
      return handleCORS(
        NextResponse.json({
          success: true,
          service: "NeoNoble Ramp API",
          status: "online"
        })
      )
    }

    // STATUS POST
    if (route === "/status" && method === "POST") {
      const body = await request.json()

      if (!body.client_name) {
        return handleCORS(
          NextResponse.json(
            { error: "client_name is required" },
            { status: 400 }
          )
        )
      }

      return handleCORS(
        NextResponse.json({
          success: true,
          received: body
        })
      )
    }

    // STATUS GET
    if (route === "/status" && method === "GET") {
      return handleCORS(
        NextResponse.json({
          success: true,
          api: "running"
        })
      )
    }

    // ONRAMP legacy path, backed by the persistent ledger.
    if (route === "/onramp" && method === "POST") {
      const body = await request.json()
      const transaction = await createLedgerTransactionFromRequest("onramp", {
        ...body,
        toToken: body.toToken || "NENO",
      })

      return handleCORS(
        NextResponse.json({
          success: true,
          type: "onramp",
          transactionId: transaction.id,
          currentStep: transaction.step,
          data: body,
          status: transaction.status
        })
      )
    }

    // OFFRAMP legacy path, backed by the persistent ledger.
    if (route === "/offramp" && method === "POST") {
      const body = await request.json()
      const transaction = await createLedgerTransactionFromRequest("offramp", {
        ...body,
        fromToken: body.fromToken || "NENO",
      })
      return handleCORS(
        NextResponse.json({
          success: true,
          type: "offramp",
          transactionId: transaction.id,
          txHash: transaction.txHash,
          currentStep: transaction.step,
          chainStatus: transaction.chainStatus,
          estimatedCompletion: null,
          data: body,
          status: transaction.status
        })
      )
    }

    // SWAP legacy path, backed by the persistent ledger.
    if (route === "/swap" && method === "POST") {
      const body = await request.json()
      const transaction = await createLedgerTransactionFromRequest("swap", {
        ...body,
        fromToken: body.fromToken || "NENO",
        toToken: body.toToken || "USDC",
      })

      return handleCORS(
        NextResponse.json({
          success: true,
          type: "swap",
          transactionId: transaction.id,
          currentStep: transaction.step,
          data: body,
          status: transaction.status
        })
      )
    }

    return handleCORS(
      NextResponse.json(
        { error: `Route ${route} not found` },
        { status: 404 }
      )
    )

  } catch (error) {
    console.error("API Error:", error)

    return handleCORS(
      NextResponse.json(
        {
          success: false,
          error: error.message
        },
        { status: 500 }
      )
    )
  }
}

export const GET = handleRoute
export const POST = handleRoute
export const OPTIONS = async () => {
  return handleCORS(new NextResponse(null, { status: 204 }))
}

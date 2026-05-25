import { createRequire } from "node:module"
import { NextResponse } from "next/server"

const require = createRequire(import.meta.url)
const { getTransactionStatusOnChain } = require("../../../../../lib/blockchain/walletService.cjs")

export async function GET(request, { params }) {
  try {
    const chain = request.nextUrl.searchParams.get("chain") || "BSC"
    return NextResponse.json(await getTransactionStatusOnChain(params.hash, chain))
  } catch (error) {
    return NextResponse.json(
      { error: error.message || "Unable to read chain status", txHash: params.hash },
      { status: 400 },
    )
  }
}

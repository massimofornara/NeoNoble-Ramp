import { NextResponse } from "next/server"
import { prisma } from "@/lib/db"
import { getUserTransactions } from "@/lib/ledger/ledgerService"

export async function GET(request) {
  const userId = request.nextUrl.searchParams.get("userId")
  const limit = Math.min(Number(request.nextUrl.searchParams.get("limit") || 100), 500)

  const transactions = userId
    ? await getUserTransactions(userId)
    : await prisma.transaction.findMany({ orderBy: { createdAt: "desc" }, take: limit })
  return NextResponse.json({
    userId: userId || null,
    transactions: transactions.map((transaction) => ({
      id: transaction.id,
      type: transaction.type,
      status: transaction.status,
      chainStatus: transaction.chainStatus,
      fromToken: transaction.fromToken,
      toToken: transaction.toToken,
      cryptoAmount: transaction.cryptoAmount,
      fiatAmount: transaction.fiatAmount,
      fiatCurrency: transaction.fiatCurrency,
      network: transaction.network,
      chainId: transaction.chainId,
      chainName: transaction.chainName,
      txHash: transaction.txHash,
      step: transaction.step,
      blockNumber: transaction.blockNumber,
      gasUsed: transaction.gasUsed,
      confirmations: transaction.confirmations,
      finalityStatus: transaction.finalityStatus,
      settlementLayer: transaction.settlementLayer,
      fromAddress: transaction.fromAddress,
      toAddress: transaction.toAddress,
      settlementId: transaction.settlementId,
      paymentReference: transaction.paymentReference,
      executionAttempts: transaction.executionAttempts,
      fallbackPath: transaction.fallbackPath,
      lastSuccessfulRail: transaction.lastSuccessfulRail,
      errorMessage: transaction.errorMessage,
      createdAt: transaction.createdAt,
      updatedAt: transaction.updatedAt,
    })),
  })
}

import { NextResponse } from "next/server"
import { prisma } from "@/lib/db"

export async function GET(_request, { params }) {
  const hash = params.hash
  const transaction = await prisma.transaction.findFirst({
    where: { txHash: hash },
    include: {
      events: {
        orderBy: { createdAt: "asc" },
      },
    },
  })

  if (!transaction) {
    return NextResponse.json({ error: "transaction not found", txHash: hash }, { status: 404 })
  }

  return NextResponse.json(transaction)
}

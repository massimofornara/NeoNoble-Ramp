import { NextResponse } from "next/server"
import { getUserBalance } from "@/lib/ledger/ledgerService"

export async function GET(request) {
  const userId = request.nextUrl.searchParams.get("userId")
  if (!userId) {
    return NextResponse.json({ error: "userId is required" }, { status: 400 })
  }

  return NextResponse.json(await getUserBalance(userId))
}

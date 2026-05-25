import { NextResponse } from "next/server"
import crypto from "node:crypto"
import { prisma } from "@/lib/db"

function timingSafeEqualHex(a, b) {
  const left = Buffer.from(String(a || "").replace(/^sha256=/, ""), "hex")
  const right = Buffer.from(String(b || "").replace(/^sha256=/, ""), "hex")
  return left.length === right.length && crypto.timingSafeEqual(left, right)
}

function verifySettlementSignature(request, rawBody) {
  const secret = process.env.SETTLEMENT_WEBHOOK_SECRET
  if (!secret) {
    throw new Error("SETTLEMENT_WEBHOOK_SECRET is required for generic settlement webhooks")
  }

  const signature =
    request.headers.get("x-settlement-signature") ||
    request.headers.get("x-signature")
  const timestamp = request.headers.get("x-settlement-timestamp")

  if (!signature || !timestamp) {
    throw new Error("Missing settlement webhook signature headers")
  }

  const ageMs = Math.abs(Date.now() - Number(timestamp))
  if (!Number.isFinite(ageMs) || ageMs > 5 * 60 * 1000) {
    throw new Error("Settlement webhook timestamp is outside the replay window")
  }

  const expected = crypto
    .createHmac("sha256", secret)
    .update(`${timestamp}.${rawBody}`)
    .digest("hex")

  if (!timingSafeEqualHex(signature, expected)) {
    throw new Error("Invalid settlement webhook signature")
  }
}

export async function POST(request) {
  const rawBody = await request.text()
  try {
    verifySettlementSignature(request, rawBody)
  } catch (error) {
    return NextResponse.json({ error: error.message }, { status: 401 })
  }

  let body
  try {
    body = JSON.parse(rawBody)
  } catch {
    return NextResponse.json({ error: "Invalid JSON payload" }, { status: 400 })
  }
  const settlementId = body.settlementId || body.id
  const paymentReference = body.paymentReference || body.reference
  const providerStatus = String(body.status || "").toLowerCase()

  if (!settlementId && !paymentReference) {
    return NextResponse.json({ error: "settlementId or paymentReference is required" }, { status: 400 })
  }

  const transaction = await prisma.transaction.findFirst({
    where: {
      OR: [
        settlementId ? { settlementId: String(settlementId) } : undefined,
        paymentReference ? { paymentReference: String(paymentReference) } : undefined,
      ].filter(Boolean),
    },
  })

  if (!transaction) {
    return NextResponse.json({ error: "settlement transaction not found" }, { status: 404 })
  }

  if (["settled", "paid", "completed", "confirmed"].includes(providerStatus)) {
    const updated = await prisma.transaction.update({
      where: { id: transaction.id },
      data: {
        status: "settlement_confirmed",
        step: "finalized",
        finalityStatus: "finalized",
        chainStatus: "provider_settlement_confirmed",
        lastSuccessfulRail: transaction.settlementLayer || "settlement_provider",
      },
    })

    await prisma.transactionEvent.create({
      data: {
        transactionId: transaction.id,
        eventType: "settlement.confirmed",
        payload: body,
      },
    })

    return NextResponse.json({ success: true, transaction: updated })
  }

  if (["failed", "rejected", "returned"].includes(providerStatus)) {
    const updated = await prisma.transaction.update({
      where: { id: transaction.id },
      data: {
        status: "execution_fallback_active",
        step: "fiat_settlement_failed_retrying",
        finalityStatus: "settlement_pending",
        chainStatus: "provider_routing_active",
        errorMessage: body.error || "PSP settlement failed",
      },
    })

    await prisma.transactionEvent.create({
      data: {
        transactionId: transaction.id,
        eventType: "settlement.provider_failed_retrying",
        payload: body,
      },
    })

    return NextResponse.json({ success: true, transaction: updated })
  }

  return NextResponse.json({ success: true, ignored: true, transactionId: transaction.id })
}

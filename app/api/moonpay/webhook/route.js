import crypto from "node:crypto"
import { NextResponse } from "next/server"
import { prisma } from "@/lib/db"
import { getMoonPayConfig } from "@/lib/execution/providerConfig"

function parseSignature(header) {
  return Object.fromEntries(
    String(header || "")
      .split(",")
      .map((part) => part.split("=").map((piece) => piece.trim()))
      .filter(([key, value]) => key && value),
  )
}

function verifySignature(rawBody, request) {
  const config = getMoonPayConfig()
  if (!config.webhookApiKey) {
    throw new Error("MOONPAY_WEBHOOK_API_KEY is required for MoonPay webhook verification")
  }

  const header = request.headers.get("Moonpay-Signature-V2") || request.headers.get("moonpay-signature-v2")
  const parsed = parseSignature(header)
  if (!parsed.t || !parsed.s) throw new Error("Missing Moonpay-Signature-V2 header")

  const signedPayload = `${parsed.t}.${rawBody}`
  const expected = crypto.createHmac("sha256", config.webhookApiKey).update(signedPayload).digest("hex")
  const received = Buffer.from(parsed.s, "hex")
  const computed = Buffer.from(expected, "hex")
  if (received.length !== computed.length || !crypto.timingSafeEqual(received, computed)) {
    throw new Error("Invalid MoonPay webhook signature")
  }
}

function getTransactionId(payload) {
  return (
    payload?.externalTransactionId ||
    payload?.data?.externalTransactionId ||
    payload?.transaction?.externalTransactionId ||
    payload?.data?.transaction?.externalTransactionId ||
    payload?.metadata?.transactionId
  )
}

function getProviderId(payload) {
  return (
    payload?.id ||
    payload?.data?.id ||
    payload?.transactionId ||
    payload?.transaction?.id ||
    payload?.data?.transaction?.id
  )
}

function normalizeStatus(payload) {
  const status = String(
    payload?.status ||
      payload?.data?.status ||
      payload?.transactionStatus ||
      payload?.transaction?.status ||
      payload?.data?.transaction?.status ||
      "",
  ).toLowerCase()

  if (["completed", "paid", "succeeded", "success", "sent"].includes(status)) return "settlement_confirmed"
  if (["failed", "cancelled", "canceled", "expired", "rejected"].includes(status)) return "execution_fallback_active"
  return "settlement_pending"
}

export async function POST(request) {
  try {
    const rawBody = await request.text()
    verifySignature(rawBody, request)
    const payload = JSON.parse(rawBody)
    const transactionId = getTransactionId(payload)
    if (!transactionId) {
      return NextResponse.json({ error: "MoonPay webhook missing externalTransactionId" }, { status: 400 })
    }

    const providerId = String(getProviderId(payload) || transactionId)
    const status = normalizeStatus(payload)
    const eventType =
      status === "settlement_confirmed"
        ? "provider.moonpay.settlement_confirmed"
        : status === "execution_fallback_active"
          ? "provider.moonpay.failed"
          : "provider.moonpay.updated"

    const transaction = await prisma.transaction.update({
      where: { id: String(transactionId) },
      data: {
        status,
        step: status === "settlement_confirmed" ? "finalized" : status === "execution_fallback_active" ? "provider_failed_retrying" : "provider_settlement_pending",
        settlementLayer: "moonpay",
        settlementId: providerId,
        finalityStatus: status === "settlement_confirmed" ? "finalized" : "settlement_pending",
        chainStatus: status === "settlement_confirmed" ? "provider_settlement_confirmed" : "provider_routing_active",
        lastSuccessfulRail: status === "settlement_confirmed" ? "moonpay" : undefined,
        rawTxData: payload,
        errorMessage: status === "execution_fallback_active" ? JSON.stringify(payload?.failureReason || payload?.error || payload?.data?.error || null) : null,
      },
    })

    await prisma.transactionEvent.create({
      data: {
        transactionId: transaction.id,
        eventType,
        payload,
      },
    })

    return NextResponse.json({ ok: true, transactionId: transaction.id, status: transaction.status })
  } catch (error) {
    return NextResponse.json({ ok: false, error: error.message || "MoonPay webhook failed" }, { status: 400 })
  }
}

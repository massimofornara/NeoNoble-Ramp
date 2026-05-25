import { NextResponse } from "next/server"
import { signMoonPayUrl } from "@/lib/execution/providerConfig"

export async function POST(request) {
  try {
    const body = await request.json()
    const urlForSignature = String(body.urlForSignature || body.url || "")
    if (!urlForSignature.startsWith("https://")) {
      return NextResponse.json({ error: "urlForSignature must be an HTTPS MoonPay widget URL" }, { status: 400 })
    }

    const hostname = new URL(urlForSignature).hostname
    if (!hostname.endsWith("moonpay.com")) {
      return NextResponse.json({ error: "Only MoonPay widget URLs can be signed" }, { status: 400 })
    }

    return NextResponse.json({
      signature: signMoonPayUrl(urlForSignature, process.env.MOONPAY_SECRET_KEY),
    })
  } catch (error) {
    return NextResponse.json({ error: error.message || "Unable to sign MoonPay URL" }, { status: 400 })
  }
}

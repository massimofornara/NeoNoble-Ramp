import { createRequire } from "node:module"
import { NextResponse } from "next/server"

const require = createRequire(import.meta.url)
const { CHAIN_CONFIGS } = require("../../../lib/chains/chainConfig.cjs")
const { listImplementedAdapters } = require("../../../lib/chains/adapters.cjs")

export async function GET() {
  return NextResponse.json({
    supportedChains: Object.values(CHAIN_CONFIGS).map((chain) => ({
      key: chain.key,
      chainId: chain.chainId,
      chainName: chain.chainName,
      settlementLayer: chain.settlementLayer,
    })),
    adapters: listImplementedAdapters(),
  })
}

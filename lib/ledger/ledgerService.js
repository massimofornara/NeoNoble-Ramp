import { prisma } from "../db.js"

const SCALE = 18n
const BASE = 10n ** SCALE

function normalizeToken(token) {
  return token ? String(token).trim().toUpperCase() : undefined
}

function normalizeNetwork(network) {
  return String(network || "BSC").trim().toUpperCase()
}

function getChainMetadata(network) {
  const key = normalizeNetwork(network)
  if (key === "ETH" || key === "ETHEREUM" || key === "MAINNET") {
    return { network: "ETHEREUM", chainId: 1, chainName: "Ethereum", settlementLayer: "ethereum" }
  }
  if (key === "ARBITRUM" || key === "ARB") {
    return { network: "ARBITRUM", chainId: 42161, chainName: "Arbitrum", settlementLayer: "arbitrum" }
  }
  if (key === "OPTIMISM" || key === "OP") {
    return { network: "OPTIMISM", chainId: 10, chainName: "Optimism", settlementLayer: "optimism" }
  }
  if (key === "ZKSYNC" || key === "ZKSYNC_ERA") {
    return { network: "ZKSYNC", chainId: 324, chainName: "zkSync", settlementLayer: "zksync" }
  }
  return { network: "BSC", chainId: 56, chainName: "BSC", settlementLayer: "bsc" }
}

function hasProviderSettlementProof(transaction) {
  return (
    Boolean(transaction.settlementId) &&
    ["settled", "settlement_confirmed"].includes(String(transaction.finalityStatus || "").toLowerCase()) &&
    ["transak", "moonpay", "stripe"].includes(String(transaction.settlementLayer || "").toLowerCase())
  )
}

function isSettlementConfirmed(status) {
  return ["confirmed", "settled", "finalized", "settlement_confirmed"].includes(String(status || "").toLowerCase())
}

function toNullableString(value) {
  if (value === undefined || value === null || value === "") return undefined
  return String(value)
}

function decimalToScaled(value) {
  if (value === undefined || value === null || value === "") return 0n
  const raw = String(value).trim()
  if (!/^-?\d+(\.\d+)?$/.test(raw)) {
    throw new Error(`Invalid decimal amount: ${raw}`)
  }

  const negative = raw.startsWith("-")
  const unsigned = negative ? raw.slice(1) : raw
  const [whole, fraction = ""] = unsigned.split(".")
  const padded = (fraction + "0".repeat(Number(SCALE))).slice(0, Number(SCALE))
  const scaled = BigInt(whole || "0") * BASE + BigInt(padded || "0")
  return negative ? -scaled : scaled
}

function scaledToDecimal(value) {
  const negative = value < 0n
  const unsigned = negative ? -value : value
  const whole = unsigned / BASE
  const fraction = unsigned % BASE
  const fractionText = fraction.toString().padStart(Number(SCALE), "0").replace(/0+$/, "")
  return `${negative ? "-" : ""}${whole.toString()}${fractionText ? `.${fractionText}` : ""}`
}

function multiplyDecimal(value, multiplier) {
  return scaledToDecimal((decimalToScaled(value) * decimalToScaled(multiplier)) / BASE)
}

export async function createTransaction(data) {
  const chain = getChainMetadata(data.network)
  const transaction = await prisma.transaction.create({
    data: {
      userId: String(data.userId),
      type: String(data.type).toLowerCase(),
      status: "routing_active",
      fromToken: normalizeToken(data.fromToken),
      toToken: normalizeToken(data.toToken),
      cryptoAmount: toNullableString(data.cryptoAmount),
      fiatAmount: toNullableString(data.fiatAmount),
      fiatCurrency: data.fiatCurrency ? String(data.fiatCurrency).toUpperCase() : undefined,
      network: chain.network,
      chainId: chain.chainId,
      chainName: chain.chainName,
      settlementLayer: chain.settlementLayer,
      fromAddress: data.fromAddress ? String(data.fromAddress) : undefined,
      toAddress: data.toAddress ? String(data.toAddress) : undefined,
      paymentReference: data.paymentReference ? String(data.paymentReference) : undefined,
      settlementId: data.settlementId ? String(data.settlementId) : undefined,
      chainStatus: "queued",
      finalityStatus: "queued",
      step: "init",
      executionAttempts: [],
      fallbackPath: [],
    },
  })

  await prisma.transactionEvent.create({
    data: {
      transactionId: transaction.id,
      eventType: "transaction.created",
      payload: {
        userId: transaction.userId,
        type: transaction.type,
        fromToken: transaction.fromToken,
        toToken: transaction.toToken,
        cryptoAmount: transaction.cryptoAmount,
        fiatAmount: transaction.fiatAmount,
        network: transaction.network,
      },
    },
  })

  return transaction
}

export async function updateTransaction(id, data) {
  return prisma.transaction.update({
    where: { id },
    data,
  })
}

export async function getUserTransactions(userId) {
  return prisma.transaction.findMany({
    where: { userId: String(userId) },
    orderBy: { createdAt: "desc" },
  })
}

export async function getUserBalance(userId) {
  const transactions = await prisma.transaction.findMany({
    where: { userId: String(userId) },
    select: {
      type: true,
      status: true,
      fromToken: true,
      toToken: true,
      cryptoAmount: true,
      fiatAmount: true,
      fiatCurrency: true,
      txHash: true,
      blockNumber: true,
      chainStatus: true,
      finalityStatus: true,
      settlementId: true,
      settlementLayer: true,
    },
  })

  let nenoBalance = 0n
  let eurPending = 0n
  const assetBalances = new Map()
  const pendingFiatBalances = new Map()

  function addAsset(asset, amount) {
    if (!asset) return
    const normalized = normalizeToken(asset)
    assetBalances.set(normalized, (assetBalances.get(normalized) || 0n) + amount)
  }

  function addPendingFiat(currency, amount) {
    const normalized = currency ? String(currency).toUpperCase() : "EUR"
    pendingFiatBalances.set(normalized, (pendingFiatBalances.get(normalized) || 0n) + amount)
  }

  for (const transaction of transactions) {
    const type = transaction.type.toLowerCase()
    const status = transaction.status.toLowerCase()
    const fromToken = normalizeToken(transaction.fromToken)
    const toToken = normalizeToken(transaction.toToken)
    const amount = decimalToScaled(transaction.cryptoAmount)
    const fiatAmount = decimalToScaled(transaction.fiatAmount)
    const fiatCurrency = transaction.fiatCurrency ? transaction.fiatCurrency.toUpperCase() : "EUR"

    const hasChainProof =
      Boolean(transaction.txHash) &&
      transaction.blockNumber !== null &&
      ["confirmed", "finalized"].includes(String(transaction.chainStatus || "").toLowerCase())
    const hasSettlementProof = hasProviderSettlementProof(transaction)

    if (isSettlementConfirmed(status) && (hasChainProof || hasSettlementProof)) {
      if ((type === "onramp" || type === "swap") && toToken === "NENO") {
        nenoBalance += amount
      }

      if ((type === "offramp" || type === "swap") && fromToken === "NENO") {
        nenoBalance -= amount
      }

      if (type === "onramp") {
        addAsset(toToken, amount)
      }

      if (type === "offramp") {
        addAsset(fromToken, -amount)
        addAsset(fiatCurrency, fiatAmount)
      }

      if (type === "swap") {
        addAsset(fromToken, -amount)
        addAsset(toToken, fiatAmount || amount)
      }
    }

    if (
      type === "offramp" &&
      (status === "broadcasting" || status === "broadcasted")
    ) {
      if (!transaction.fiatCurrency || transaction.fiatCurrency.toUpperCase() === "EUR") {
        eurPending += fiatAmount
      }
      addPendingFiat(fiatCurrency, fiatAmount)
    }
  }

  const balances = Object.fromEntries(
    Array.from(assetBalances.entries()).map(([asset, amount]) => [asset, scaledToDecimal(amount)]),
  )

  const pendingBalances = Object.fromEntries(
    Array.from(pendingFiatBalances.entries()).map(([asset, amount]) => [asset, scaledToDecimal(amount)]),
  )

  return {
    userId: String(userId),
    nenoBalance: scaledToDecimal(nenoBalance),
    eurPending: scaledToDecimal(eurPending),
    balances: {
      NENO: balances.NENO || "0",
      USDT: balances.USDT || "0",
      EUR: balances.EUR || "0",
      ...balances,
    },
    pendingBalances,
    wallets: Object.entries({
      NENO: balances.NENO || "0",
      USDT: balances.USDT || "0",
      EUR: balances.EUR || "0",
      ...balances,
    }).map(([asset, balance]) => ({
      asset,
      balance,
      source: "transaction_ledger",
      synchronizedAt: new Date().toISOString(),
    })),
    status: "synced",
  }
}

export async function createLedgerTransactionFromRequest(type, body) {
  if (!body.userId) {
    throw new Error("userId is required")
  }

  const fromToken = normalizeToken(body.fromToken)
  const toToken = normalizeToken(body.toToken)
  const cryptoAmount = body.cryptoAmount || body.amount || body.tokens
  const fixedPrice = body.price || process.env.NENO_FIXED_PRICE_USDT || "1000"
  const derivedFiatAmount =
    !body.fiatAmount && fromToken === "NENO" && toToken === "USDT" && cryptoAmount
      ? multiplyDecimal(cryptoAmount, fixedPrice)
      : body.fiatAmount || body.amountFiat

  return createTransaction({
    userId: body.userId,
    type,
    fromToken,
    toToken,
    cryptoAmount,
    fiatAmount: derivedFiatAmount,
    fiatCurrency: body.fiatCurrency || body.fromFiat || toToken || "EUR",
    network: body.network || body.chain || "BSC",
    fromAddress: body.fromAddress,
    toAddress: body.toAddress || body.walletAddress || body.destinationAddress || body.payoutAddress,
    paymentReference: body.paymentReference || body.iban || body.payoutReference,
  })
}

export async function getUserLedgerReconciliation(userId) {
  const transactions = await prisma.transaction.findMany({
    where: { userId: String(userId) },
    orderBy: { createdAt: "desc" },
  })
  const balance = await getUserBalance(userId)
  const assetMovements = new Map()
  const unsettled = []

  function addMovement(asset, amount, transactionId) {
    if (!asset) return
    const normalized = normalizeToken(asset)
    const current = assetMovements.get(normalized) || { asset: normalized, amount: 0n, transactionIds: [] }
    current.amount += amount
    current.transactionIds.push(transactionId)
    assetMovements.set(normalized, current)
  }

  for (const transaction of transactions) {
    const type = transaction.type.toLowerCase()
    const status = transaction.status.toLowerCase()
    const fromToken = normalizeToken(transaction.fromToken)
    const toToken = normalizeToken(transaction.toToken)
    const amount = decimalToScaled(transaction.cryptoAmount)
    const fiatAmount = decimalToScaled(transaction.fiatAmount)
    const fiatCurrency = transaction.fiatCurrency ? transaction.fiatCurrency.toUpperCase() : undefined

    const hasChainProof =
      Boolean(transaction.txHash) &&
      transaction.blockNumber !== null &&
      ["confirmed", "finalized"].includes(String(transaction.chainStatus || "").toLowerCase())
    const hasSettlementProof = hasProviderSettlementProof(transaction)

    if (!isSettlementConfirmed(status) || !(hasChainProof || hasSettlementProof)) {
      unsettled.push({
        id: transaction.id,
        type: transaction.type,
        status: transaction.status,
        step: transaction.step,
      })
      continue
    }

    if (type === "onramp") {
      addMovement(toToken, amount, transaction.id)
    }

    if (type === "offramp") {
      addMovement(fromToken, -amount, transaction.id)
      addMovement(fiatCurrency, fiatAmount, transaction.id)
    }

    if (type === "swap") {
      addMovement(fromToken, -amount, transaction.id)
      addMovement(toToken, fiatAmount || amount, transaction.id)
    }
  }

  return {
    userId: String(userId),
    status: unsettled.length === 0 ? "reconciled" : "unsettled",
    unsettled,
    movementSums: Object.fromEntries(
      Array.from(assetMovements.entries()).map(([asset, movement]) => [
        asset,
        {
          amount: scaledToDecimal(movement.amount),
          transactionIds: movement.transactionIds,
        },
      ]),
    ),
    balances: balance.balances,
    pendingBalances: balance.pendingBalances,
    transactionCount: transactions.length,
    checkedAt: new Date().toISOString(),
  }
}

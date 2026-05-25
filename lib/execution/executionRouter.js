import { prisma } from "../db.js"
import { canUseOnChainExecutor } from "./onChainExecutor.js"
import { createMoonPayWidgetAction } from "./moonpayRailExecutor.js"
import { createStripeSettlementAction } from "./stripeRailExecutor.js"
import { createTransakWidgetAction } from "./transakRailExecutor.js"
import { createWisePayoutAction } from "./wiseRailExecutor.js"
import { createRequire } from "node:module"

const require = createRequire(import.meta.url)
const { buildLiquidityPlan, markLiquidityPending } = require("../liquidity/liquidityManager.cjs")
const { runLiquidityBootstrap } = require("../liquidity/bootstrapLayer.cjs")
const { resolveSettlementGate } = require("../settlement/settlementGateResolver.cjs")

function normalizeAttempts(value) {
  return Array.isArray(value) ? value : []
}

function nowIso() {
  return new Date().toISOString()
}

function publicAttempt(attempt) {
  return {
    rail: attempt.rail,
    status: attempt.status,
    reason: attempt.reason,
    attemptedAt: attempt.attemptedAt,
    actionType: attempt.actionType,
  }
}

async function recordEvent(transactionId, eventType, payload = {}) {
  await prisma.transactionEvent.create({
    data: {
      transactionId,
      eventType,
      payload,
    },
  })
}

async function loadFresh(transaction) {
  return prisma.transaction.findUnique({ where: { id: transaction.id } })
}

async function updateRoutingState(transaction, data, eventType, eventPayload = {}) {
  const updated = await prisma.transaction.update({
    where: { id: transaction.id },
    data,
  })
  await recordEvent(transaction.id, eventType, eventPayload)
  return updated
}

async function appendAttempt(transaction, attempt) {
  const fresh = await loadFresh(transaction)
  const attempts = normalizeAttempts(fresh?.executionAttempts)
  const nextAttempt = { ...attempt, attemptedAt: nowIso() }
  const nextAttempts = [...attempts, nextAttempt]
  await prisma.transaction.update({
    where: { id: transaction.id },
    data: {
      executionAttempts: nextAttempts,
      fallbackPath: nextAttempts.map(publicAttempt),
      errorMessage:
        attempt.status === "failed"
          ? nextAttempts
              .filter((entry) => entry.status === "failed")
              .map((entry) => `${entry.rail}: ${entry.reason}`)
              .join(" | ")
          : fresh?.errorMessage || undefined,
    },
  })
  await recordEvent(transaction.id, `execution.${attempt.status}`, nextAttempt)
  return nextAttempts
}

async function selectOnChain(transaction, preflight) {
  const attempts = await appendAttempt(transaction, {
    rail: "onchain",
    status: "selected",
    reason: "on-chain execution path available",
    actionType: "worker",
    preflight,
  })

  const updated = await updateRoutingState(
    transaction,
    {
      status: "routing_active",
      step: "onchain_execution_queued",
      chainStatus: "queued",
      finalityStatus: "routing_active",
      settlementLayer: preflight.chain.settlementLayer,
      lastSuccessfulRail: "onchain",
      executionAttempts: attempts,
      fallbackPath: attempts.map(publicAttempt),
      rawTxData: {
        selectedProvider: "onchain",
        preflight,
        executionAttempts: attempts,
      },
    },
    "execution.route_selected",
    {
      rail: "onchain",
      chain: preflight.chain,
    },
  )

  return {
    transaction: updated,
    route: {
      provider: "onchain",
      type: "worker",
      status: "routing_active",
      preflight,
      executionAttempts: attempts.map(publicAttempt),
    },
  }
}

async function selectProviderAction(transaction, provider, action, attempts) {
  const nextAttempts = [
    ...attempts,
    {
      rail: provider,
      status: "selected",
      reason: "provider action available",
      actionType: action.type,
      attemptedAt: nowIso(),
    },
  ]

  const updated = await updateRoutingState(
    transaction,
    {
      status: action.settlementId ? "execution_successful" : "execution_fallback_active",
      step: action.settlementId ? `${provider}_execution_successful` : `${provider}_execution_action_required`,
      settlementLayer: provider,
      finalityStatus: "settlement_pending",
      chainStatus: "provider_routing_active",
      settlementId: action.settlementId || undefined,
      lastSuccessfulRail: provider,
      executionAttempts: nextAttempts,
      fallbackPath: nextAttempts.map(publicAttempt),
      rawTxData: {
        provider,
        action,
        executionAttempts: nextAttempts,
        fallbackPath: nextAttempts.map(publicAttempt),
      },
    },
    action.settlementId ? "execution.successful" : "execution.fallback_active",
    {
      provider,
      actionType: action.type,
      settlementId: action.settlementId || null,
      fallbackPath: nextAttempts.map(publicAttempt),
    },
  )

  return { transaction: updated, route: action }
}

async function activateDeferredSettlement(transaction, attempts) {
  const deferredAttempt = {
    rail: "deferred_settlement",
    status: "selected",
    reason: "all live rails unavailable; continuing in deferred settlement queue",
    actionType: "deferred_queue",
    attemptedAt: nowIso(),
  }
  const nextAttempts = [...attempts, deferredAttempt]

  const updated = await updateRoutingState(
    transaction,
    {
      status: "settlement_pending",
      step: "deferred_settlement_active",
      settlementLayer: "deferred",
      chainStatus: "deferred_settlement",
      finalityStatus: "settlement_pending",
      lastSuccessfulRail: "deferred_settlement",
      executionAttempts: nextAttempts,
      fallbackPath: nextAttempts.map(publicAttempt),
      rawTxData: {
        selectedProvider: "deferred_settlement",
        actionRequired: "retry_provider_routing_until_webhook_or_chain_confirmation",
        executionAttempts: nextAttempts,
        fallbackPath: nextAttempts.map(publicAttempt),
      },
      errorMessage: nextAttempts
        .filter((entry) => entry.status === "failed")
        .map((entry) => `${entry.rail}: ${entry.reason}`)
        .join(" | "),
    },
    "execution.deferred_settlement_active",
    {
      selectedProvider: "deferred_settlement",
      fallbackPath: nextAttempts.map(publicAttempt),
    },
  )

  return {
    transaction: updated,
    route: {
      provider: "deferred_settlement",
      type: "deferred_queue",
      status: "settlement_pending",
      actionRequired: "keep retrying execution rails; no balance impact until settlement_confirmed",
      fallbackPath: nextAttempts.map(publicAttempt),
    },
  }
}

async function activateLiquidityPending(transaction, attempts, options = {}) {
  const fresh = await loadFresh(transaction)
  const plan = await buildLiquidityPlan(fresh || transaction, options)
  const bootstrap = await runLiquidityBootstrap(prisma, fresh || transaction, { liquidityPlan: plan, state: options.state })
  const gate = await resolveSettlementGate(prisma, fresh || transaction, bootstrap.postFundingPlan, bootstrap)
  if (gate.open && !options.afterBootstrap) {
    const ready = await loadFresh(transaction)
    return routeExecution(ready, { ...options, afterBootstrap: true })
  }
  const updated =
    gate.transaction ||
    (await markLiquidityPending(prisma, fresh || transaction, bootstrap.postFundingPlan || plan))
  const nextAttempts = [
    ...attempts,
    {
      rail: "liquidity_orchestrator",
      status: bootstrap.status,
      reason:
        bootstrap.status === "funding_requested"
          ? "auto-funding orchestrator requested real funding and is awaiting provider proof"
          : "no provider, treasury, or configured bootstrap adapter has enough verified liquidity for settlement",
      actionType: "liquidity_bootstrap",
      attemptedAt: nowIso(),
      blockers: bootstrap.postFundingPlan.blockers,
      bootstrap: {
        status: bootstrap.status,
        outcomes: bootstrap.outcomes.map((outcome) => ({
          provider: outcome.provider,
          status: outcome.status,
          asset: outcome.asset,
          providerReference: outcome.providerReference,
          txHash: outcome.txHash,
          settlementId: outcome.settlementId,
          error: outcome.error,
        })),
      },
    },
  ]
  await prisma.transaction.update({
    where: { id: updated.id },
    data: {
      executionAttempts: nextAttempts,
      fallbackPath: nextAttempts.map(publicAttempt),
    },
  })

  return {
    transaction: { ...updated, executionAttempts: nextAttempts, fallbackPath: nextAttempts.map(publicAttempt) },
    route: {
      provider: "liquidity_orchestrator",
      type: "liquidity_queue",
      status: "execution_attempted",
      actionRequired:
        bootstrap.status === "funding_requested"
          ? "await funding provider proof; worker will resync liquidity and retry automatically"
          : "configure a real liquidity bootstrap adapter or fund treasury/provider rail; worker will retry automatically",
      required: bootstrap.postFundingPlan.required,
      blockers: bootstrap.postFundingPlan.blockers,
      providers: bootstrap.postFundingPlan.state.providers,
      bootstrap,
      gate: gate.payload,
    },
  }
}

async function tryRail(transaction, attempts, rail, createAction) {
  try {
    const action = await createAction()
    return { ok: true, action, attempts }
  } catch (error) {
    const nextAttempts = await appendAttempt(transaction, {
      rail,
      status: "failed",
      reason: error.message,
      actionType: "route_attempt",
    })
    return { ok: false, attempts: nextAttempts }
  }
}

async function rejectOnChain(transaction, onChain) {
  const attempts = await appendAttempt(transaction, {
    rail: "onchain",
    status: "failed",
    reason: onChain.reason,
    actionType: "preflight",
    preflight: onChain.preflight,
  })
  await updateRoutingState(
    transaction,
    {
      status: "execution_attempted",
      step: "onchain_unavailable_trying_fallbacks",
      chainStatus: "route_rejected",
      finalityStatus: "routing_active",
      settlementLayer: onChain.preflight?.chain?.settlementLayer || transaction.settlementLayer,
      executionAttempts: attempts,
      fallbackPath: attempts.map(publicAttempt),
      rawTxData: {
        selectedProvider: null,
        executionAttempts: attempts,
        fallbackPath: attempts.map(publicAttempt),
      },
    },
    "execution.route_attempted",
    {
      rail: "onchain",
      reason: onChain.reason,
    },
  )
  return attempts
}

export async function routeExecution(transaction, options = {}) {
  const onChain = await canUseOnChainExecutor(transaction)

  if (onChain.ok) {
    return selectOnChain(transaction, onChain.preflight)
  }

  let attempts = await rejectOnChain(transaction, onChain)
  const liquidityPlan = await buildLiquidityPlan(transaction)

  if (!liquidityPlan.canSettle) {
    return activateLiquidityPending(transaction, attempts, { state: liquidityPlan.state })
  }

  const orderedRails =
    transaction.type === "swap"
      ? [
          ["stripe", () => createStripeSettlementAction(transaction)],
          ["moonpay", () => createMoonPayWidgetAction(transaction, { ...options, flow: "swap" })],
          ["transak", () => createTransakWidgetAction(transaction, { ...options, productsAvailed: "BUY,SELL" })],
        ]
      : transaction.type === "offramp"
        ? [
            ...(liquidityPlan.selected?.provider === "wise" ? [["wise", () => createWisePayoutAction(transaction)]] : []),
            ...(liquidityPlan.selected?.provider === "stripe" ? [["stripe", () => createStripeSettlementAction(transaction)]] : []),
            ["moonpay", () => createMoonPayWidgetAction(transaction, { ...options, flow: "sell" })],
            ["transak", () => createTransakWidgetAction(transaction, options)],
          ]
        : [
            ["stripe", () => createStripeSettlementAction(transaction)],
            ["moonpay", () => createMoonPayWidgetAction(transaction, { ...options, flow: "buy" })],
            ["transak", () => createTransakWidgetAction(transaction, options)],
          ]

  for (const [rail, createAction] of orderedRails) {
    const result = await tryRail(transaction, attempts, rail, createAction)
    attempts = result.attempts
    if (result.ok) {
      return selectProviderAction(transaction, rail, result.action, attempts)
    }
  }

  return activateLiquidityPending(transaction, attempts, { state: liquidityPlan.state })
}

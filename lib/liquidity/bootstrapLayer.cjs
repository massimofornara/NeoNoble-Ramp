const crypto = require('crypto');
const {
  buildLiquidityPlan,
  getProviderLiquidityState,
  requiredSettlement,
} = require('./liquidityManager.cjs');

function isEnabled(value) {
  return ['1', 'true', 'yes', 'on'].includes(String(value || '').toLowerCase());
}

function fundingEndpointFor(asset) {
  const scoped = process.env[`${asset}_FUNDING_REQUEST_URL`] || process.env[`${asset}_LIQUIDITY_PROVIDER_URL`];
  const generic = process.env.LIQUIDITY_BOOTSTRAP_FUNDING_REQUEST_URL || process.env.LIQUIDITY_BOOTSTRAP_API_URL;
  return scoped || generic || '';
}

function fundingApiKeyFor(asset) {
  return process.env[`${asset}_LIQUIDITY_PROVIDER_API_KEY`] || process.env.LIQUIDITY_BOOTSTRAP_API_KEY || '';
}

function hasFundingAdapter(asset) {
  return Boolean(fundingEndpointFor(asset) && fundingApiKeyFor(asset));
}

function providerBalance(provider, asset) {
  const value = provider?.balances?.[String(asset).toUpperCase()];
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '0';
}

function buildUnifiedExecutionPool(state) {
  const onchain = state.providers.onchain || {};
  const stripe = state.providers.stripe || {};
  const wise = state.providers.wise || {};

  return {
    observedAt: state.observedAt,
    assets: {
      USDT: {
        asset: 'USDT',
        railType: 'crypto',
        sources: [
          {
            provider: 'onchain',
            rail: 'hot_wallet',
            configured: Boolean(onchain.address),
            executable: onchain.executionMode === 'real',
            balance: providerBalance(onchain, 'USDT'),
            address: onchain.address || null,
            proof: onchain.proof || null,
          },
          {
            provider: 'external_liquidity_bridge',
            rail: 'treasury_top_up',
            configured: hasFundingAdapter('USDT'),
            executable: hasFundingAdapter('USDT'),
            balance: null,
            endpointConfigured: Boolean(fundingEndpointFor('USDT')),
          },
        ],
      },
      EUR: {
        asset: 'EUR',
        railType: 'fiat',
        sources: [
          {
            provider: 'stripe',
            rail: 'payout',
            configured: Boolean(stripe.configured),
            executable: Boolean(stripe.configured && stripe.payoutsEnabled),
            balance: providerBalance(stripe, 'EUR'),
            proof: stripe.proof || null,
          },
          {
            provider: 'wise',
            rail: 'balance_transfer',
            configured: Boolean(wise.configured),
            executable: Boolean(wise.configured && wise.payoutsEnabled),
            balance: providerBalance(wise, 'EUR'),
            proof: wise.proof || null,
          },
          {
            provider: 'external_fiat_funding',
            rail: 'treasury_top_up',
            configured: hasFundingAdapter('EUR'),
            executable: hasFundingAdapter('EUR'),
            balance: null,
            endpointConfigured: Boolean(fundingEndpointFor('EUR')),
          },
        ],
      },
    },
  };
}

function buildBootstrapPlan(transaction, liquidityPlan) {
  const required = requiredSettlement(transaction);
  const pool = buildUnifiedExecutionPool(liquidityPlan.state);
  const assetPool = pool.assets[required.asset] || { asset: required.asset, sources: [] };
  const adapterConfigured = hasFundingAdapter(required.asset);
  const bootstrapEnabled = isEnabled(process.env.LIQUIDITY_BOOTSTRAP_ENABLED);
  const endpoint = fundingEndpointFor(required.asset);

  const action = {
    asset: required.asset,
    amount: required.amount,
    decimals: required.decimals,
    railType: required.railType,
    status: liquidityPlan.canSettle ? 'not_required' : adapterConfigured && bootstrapEnabled ? 'planned' : 'blocked',
    provider: required.asset === 'USDT' ? 'external_liquidity_bridge' : 'external_fiat_funding',
    endpointConfigured: Boolean(endpoint),
    apiKeyConfigured: Boolean(fundingApiKeyFor(required.asset)),
    destination:
      required.asset === 'USDT'
        ? transaction.toAddress || process.env.DEFAULT_SETTLEMENT_ADDRESS || liquidityPlan.state.providers.onchain?.address || null
        : transaction.paymentReference || transaction.toAddress || null,
    blocker: liquidityPlan.canSettle
      ? null
      : !bootstrapEnabled
        ? 'LIQUIDITY_BOOTSTRAP_ENABLED must be true'
        : !endpoint
          ? `${required.asset}_FUNDING_REQUEST_URL or LIQUIDITY_BOOTSTRAP_API_URL is required`
          : !fundingApiKeyFor(required.asset)
            ? `${required.asset}_LIQUIDITY_PROVIDER_API_KEY or LIQUIDITY_BOOTSTRAP_API_KEY is required`
            : null,
  };

  return {
    transactionId: transaction.id,
    required,
    pool,
    sources: assetPool.sources,
    actions: action.status === 'planned' ? [action] : [],
    blockers: action.blocker ? [{ asset: required.asset, blocker: action.blocker }] : [],
    status: liquidityPlan.canSettle ? 'not_required' : action.status === 'planned' ? 'ready_to_request' : 'blocked',
  };
}

function normalizeEndpoint(endpoint) {
  const url = new URL(endpoint);
  if (url.pathname === '/' || url.pathname === '') {
    url.pathname = '/funding-requests';
  }
  return url.toString();
}

async function requestFundingAction(transaction, action) {
  const endpoint = normalizeEndpoint(fundingEndpointFor(action.asset));
  const idempotencyKey = crypto
    .createHash('sha256')
    .update(`${transaction.id}:${action.asset}:${action.amount}`)
    .digest('hex');

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${fundingApiKeyFor(action.asset)}`,
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify({
      transactionId: transaction.id,
      userId: transaction.userId,
      asset: action.asset,
      amount: action.amount,
      railType: action.railType,
      provider: action.provider,
      chain: transaction.chainName || transaction.network || 'BSC',
      destination: action.destination,
      reason: 'settlement_liquidity_shortfall',
      metadata: {
        requestedBy: 'neonoble-auto-funding-orchestrator',
      },
    }),
  });

  const text = await response.text();
  const body = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(`Funding provider ${response.status}: ${text}`);
  }

  const reference =
    body.fundingRequestId || body.providerReference || body.reference || body.settlementId || body.txHash || body.id;
  if (!reference) {
    throw new Error('Funding provider response missing fundingRequestId/providerReference/txHash/settlementId');
  }

  return {
    ...action,
    status: 'funding_requested',
    providerReference: String(reference),
    txHash: body.txHash ? String(body.txHash) : null,
    settlementId: body.settlementId ? String(body.settlementId) : null,
    proof: {
      type: 'liquidity_funding_request',
      endpoint,
      providerReference: String(reference),
      observedAt: new Date().toISOString(),
    },
    raw: body,
  };
}

async function persistBootstrap(prisma, transaction, payload, eventType) {
  if (!prisma) return;
  const fresh = await prisma.transaction.findUnique({ where: { id: transaction.id } });
  await prisma.transaction.update({
    where: { id: transaction.id },
    data: {
      rawTxData: {
        ...(fresh?.rawTxData || transaction.rawTxData || {}),
        liquidityBootstrap: payload,
      },
    },
  });
  await prisma.transactionEvent.create({
    data: {
      transactionId: transaction.id,
      eventType,
      payload,
    },
  });
}

async function runLiquidityBootstrap(prisma, transaction, options = {}) {
  const initialPlan =
    options.liquidityPlan ||
    (await buildLiquidityPlan(transaction, {
      state: options.state,
    }));
  const bootstrapPlan = buildBootstrapPlan(transaction, initialPlan);
  const outcomes = [];

  await persistBootstrap(prisma, transaction, { bootstrapPlan, outcomes }, 'liquidity.bootstrap_planned');

  for (const action of bootstrapPlan.actions) {
    try {
      const outcome = await requestFundingAction(transaction, action);
      outcomes.push(outcome);
      await persistBootstrap(prisma, transaction, { bootstrapPlan, outcomes }, 'liquidity.bootstrap_requested');
    } catch (error) {
      outcomes.push({
        ...action,
        status: 'funding_failed',
        error: error.message,
      });
      await persistBootstrap(prisma, transaction, { bootstrapPlan, outcomes }, 'liquidity.bootstrap_failed');
    }
  }

  const postFundingState = await getProviderLiquidityState({
    chain: transaction.chainName || transaction.network || 'BSC',
  });
  const postFundingPlan = await buildLiquidityPlan(transaction, { state: postFundingState });
  const requested = outcomes.some((outcome) => outcome.status === 'funding_requested');

  return {
    transactionId: transaction.id,
    status: postFundingPlan.canSettle ? 'settlement_source_ready' : requested ? 'funding_requested' : 'blocked',
    initialPlan,
    bootstrapPlan,
    outcomes,
    postFundingPlan,
    observedAt: new Date().toISOString(),
  };
}

module.exports = {
  buildBootstrapPlan,
  buildUnifiedExecutionPool,
  runLiquidityBootstrap,
};

const Stripe = require('stripe');
const { getChainAdapter } = require('../chains/adapters.cjs');

function decimalToUnits(value, decimals = 2) {
  const text = String(value ?? '0').trim();
  if (!text || text === '.') return 0n;
  const negative = text.startsWith('-');
  const normalized = negative ? text.slice(1) : text;
  const [whole = '0', fraction = ''] = normalized.split('.');
  const units = BigInt(`${whole || '0'}${fraction.padEnd(decimals, '0').slice(0, decimals)}`);
  return negative ? -units : units;
}

function unitsToDecimal(value, decimals = 2) {
  const units = BigInt(value);
  const negative = units < 0n;
  const absolute = negative ? -units : units;
  const scale = 10n ** BigInt(decimals);
  const whole = absolute / scale;
  const fraction = (absolute % scale).toString().padStart(decimals, '0').replace(/0+$/, '');
  return `${negative ? '-' : ''}${whole.toString()}${fraction ? `.${fraction}` : ''}`;
}

function requiredSettlement(transaction) {
  if (transaction.type === 'swap') {
    return {
      asset: String(transaction.toToken || 'USDT').toUpperCase(),
      amount: String(transaction.fiatAmount || transaction.cryptoAmount || '0'),
      decimals: 18,
      railType: 'crypto',
    };
  }

  if (transaction.type === 'offramp') {
    return {
      asset: String(transaction.fiatCurrency || 'EUR').toUpperCase(),
      amount: String(transaction.fiatAmount || '0'),
      decimals: 2,
      railType: 'fiat',
    };
  }

  return {
    asset: String(transaction.toToken || transaction.fiatCurrency || '').toUpperCase(),
    amount: String(transaction.fiatAmount || transaction.cryptoAmount || '0'),
    decimals: 2,
    railType: 'unknown',
  };
}

async function syncOnChainTreasury(chain = 'BSC') {
  const adapter = getChainAdapter(chain);
  const address = await adapter.getHotWalletAddress();
  const balances = {};
  for (const asset of ['NENO', 'USDT']) {
    try {
      balances[asset] = await adapter.getTokenBalance(asset, address);
    } catch (error) {
      balances[asset] = { error: error.message };
    }
  }
  return {
    provider: 'onchain',
    chain: adapter.config.chainName,
    chainId: adapter.config.chainId,
    settlementLayer: adapter.config.settlementLayer,
    executionMode: process.env.BLOCKCHAIN_EXECUTION_MODE || 'disabled',
    address,
    native: await adapter.getNativeBalance(address),
    balances,
    proof: {
      type: 'rpc_balance',
      rpcEnv: adapter.config.rpcEnv,
      observedAt: new Date().toISOString(),
    },
  };
}

async function syncStripeTreasury() {
  if (!process.env.STRIPE_SECRET_KEY) {
    return { provider: 'stripe', configured: false, balances: {}, proof: { type: 'not_configured' } };
  }

  const stripe = new Stripe(process.env.STRIPE_SECRET_KEY, { apiVersion: '2026-04-22.dahlia' });
  const balance = await stripe.balance.retrieve(
    process.env.STRIPE_CONNECTED_ACCOUNT_ID ? { stripeAccount: process.env.STRIPE_CONNECTED_ACCOUNT_ID } : undefined,
  );
  const balances = {};
  for (const entry of balance.available || []) {
    balances[String(entry.currency).toUpperCase()] = unitsToDecimal(entry.amount, 2);
  }
  return {
    provider: 'stripe',
    configured: true,
    payoutsEnabled: process.env.STRIPE_PAYOUTS_ENABLED === 'true',
    connectedAccountId: process.env.STRIPE_CONNECTED_ACCOUNT_ID || null,
    balances,
    raw: {
      available: balance.available,
      pending: balance.pending,
      instant_available: balance.instant_available || [],
    },
    proof: {
      type: 'stripe.balance.retrieve',
      observedAt: new Date().toISOString(),
    },
  };
}

async function syncWiseTreasury() {
  const baseUrl = process.env.WISE_BASE_URL;
  const token = process.env.WISE_ACCESS_TOKEN;
  const profileId = process.env.WISE_PROFILE_ID;
  if (!baseUrl || !token || !profileId) {
    return { provider: 'wise', configured: false, balances: {}, proof: { type: 'not_configured' } };
  }

  const response = await fetch(`${baseUrl}/v4/profiles/${profileId}/balances?types=STANDARD`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(`Wise balance sync failed: ${response.status} ${JSON.stringify(body)}`);
  }

  const balances = {};
  for (const balance of body) {
    const currency = String(balance.currency?.code || balance.currency || '').toUpperCase();
    balances[currency] = String(balance.amount?.value ?? '0');
  }

  return {
    provider: 'wise',
    configured: true,
    payoutsEnabled: process.env.WISE_PAYOUTS_ENABLED === 'true',
    profileId,
    balances,
    raw: body.map((balance) => ({
      id: balance.id,
      currency: balance.currency?.code || balance.currency,
      available: balance.amount?.value,
      reserved: balance.reservedAmount?.value,
      type: balance.type,
    })),
    proof: {
      type: 'wise.v4.profile.balances',
      observedAt: new Date().toISOString(),
    },
  };
}

async function getProviderLiquidityState(options = {}) {
  const chain = options.chain || 'BSC';
  const [onchain, stripe, wise] = await Promise.all([
    syncOnChainTreasury(chain).catch((error) => ({ provider: 'onchain', error: error.message, balances: {} })),
    syncStripeTreasury().catch((error) => ({ provider: 'stripe', error: error.message, balances: {} })),
    syncWiseTreasury().catch((error) => ({ provider: 'wise', error: error.message, balances: {} })),
  ]);

  return {
    observedAt: new Date().toISOString(),
    providers: { onchain, stripe, wise },
  };
}

function balanceFor(provider, asset) {
  const value = provider?.balances?.[String(asset).toUpperCase()];
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '0';
}

function compareDecimal(left, right, decimals) {
  const leftUnits = decimalToUnits(left, decimals);
  const rightUnits = decimalToUnits(right, decimals);
  if (leftUnits === rightUnits) return 0;
  return leftUnits > rightUnits ? 1 : -1;
}

function shortfall(required, available) {
  const requiredUnits = decimalToUnits(required.amount, required.decimals);
  const availableUnits = decimalToUnits(available, required.decimals);
  return availableUnits >= requiredUnits ? '0' : unitsToDecimal(requiredUnits - availableUnits, required.decimals);
}

async function buildLiquidityPlan(transaction, options = {}) {
  const state = options.state || (await getProviderLiquidityState({ chain: transaction.chainName || transaction.network || 'BSC' }));
  const required = requiredSettlement(transaction);
  const plans = [];
  const blockers = [];

  if (required.railType === 'crypto' && required.asset === 'USDT') {
    const onchain = state.providers.onchain;
    const available = balanceFor(onchain, 'USDT');
    const canAllocate =
      onchain.executionMode === 'real' &&
      compareDecimal(available, required.amount, 18) >= 0 &&
      Boolean(transaction.toAddress || process.env.DEFAULT_SETTLEMENT_ADDRESS);
    plans.push({
      provider: 'onchain',
      rail: 'hot_wallet',
      asset: 'USDT',
      available,
      required: required.amount,
      canAllocate,
      shortfall: shortfall(required, available),
      proof: onchain.proof,
      blocker: canAllocate
        ? null
        : onchain.executionMode !== 'real'
          ? 'BLOCKCHAIN_EXECUTION_MODE must be real'
          : !transaction.toAddress && !process.env.DEFAULT_SETTLEMENT_ADDRESS
            ? 'DEFAULT_SETTLEMENT_ADDRESS or transaction.toAddress is required'
            : `insufficient USDT: ${available}/${required.amount}`,
    });
  }

  if (required.railType === 'fiat' && required.asset === 'EUR') {
    const stripe = state.providers.stripe;
    const stripeAvailable = balanceFor(stripe, 'EUR');
    const stripeCanAllocate =
      stripe.configured &&
      stripe.payoutsEnabled &&
      compareDecimal(stripeAvailable, required.amount, 2) >= 0;
    plans.push({
      provider: 'stripe',
      rail: 'payout',
      asset: 'EUR',
      available: stripeAvailable,
      required: required.amount,
      canAllocate: stripeCanAllocate,
      shortfall: shortfall(required, stripeAvailable),
      proof: stripe.proof,
      blocker: stripeCanAllocate
        ? null
        : !stripe.configured
          ? 'STRIPE_SECRET_KEY is not configured'
          : !stripe.payoutsEnabled
            ? 'STRIPE_PAYOUTS_ENABLED must be true'
            : `insufficient Stripe EUR: ${stripeAvailable}/${required.amount}`,
    });

    const wise = state.providers.wise;
    const wiseAvailable = balanceFor(wise, 'EUR');
    const wiseCanAllocate =
      wise.configured &&
      wise.payoutsEnabled &&
      compareDecimal(wiseAvailable, required.amount, 2) >= 0 &&
      Boolean(process.env.WISE_DEFAULT_BENEFICIARY_NAME || process.env.WISE_RECIPIENT_ACCOUNT_ID);
    plans.push({
      provider: 'wise',
      rail: 'balance_transfer',
      asset: 'EUR',
      available: wiseAvailable,
      required: required.amount,
      canAllocate: wiseCanAllocate,
      shortfall: shortfall(required, wiseAvailable),
      proof: wise.proof,
      blocker: wiseCanAllocate
        ? null
        : !wise.configured
          ? 'WISE_BASE_URL, WISE_ACCESS_TOKEN and WISE_PROFILE_ID are required'
          : !wise.payoutsEnabled
            ? 'WISE_PAYOUTS_ENABLED must be true'
            : !process.env.WISE_DEFAULT_BENEFICIARY_NAME && !process.env.WISE_RECIPIENT_ACCOUNT_ID
              ? 'WISE_DEFAULT_BENEFICIARY_NAME or WISE_RECIPIENT_ACCOUNT_ID is required'
              : `insufficient Wise EUR: ${wiseAvailable}/${required.amount}`,
    });
  }

  for (const plan of plans) {
    if (!plan.canAllocate && plan.blocker) blockers.push({ provider: plan.provider, blocker: plan.blocker, shortfall: plan.shortfall });
  }

  const selected = plans.find((plan) => plan.canAllocate) || null;
  return {
    transactionId: transaction.id,
    required,
    selected,
    plans,
    blockers,
    state,
    canSettle: Boolean(selected),
  };
}

async function markLiquidityPending(prisma, transaction, plan) {
  const payload = {
    required: plan.required,
    selected: plan.selected,
    blockers: plan.blockers,
    providers: plan.state.providers,
    observedAt: plan.state.observedAt,
  };

  const updated = await prisma.transaction.update({
    where: { id: transaction.id },
    data: {
      status: 'execution_attempted',
      step: 'awaiting_real_liquidity',
      chainStatus: 'funding_required',
      finalityStatus: 'execution_attempted',
      settlementLayer: plan.selected?.provider || 'liquidity_orchestrator',
      lastSuccessfulRail: plan.selected?.provider || 'liquidity_orchestrator',
      rawTxData: {
        ...(transaction.rawTxData || {}),
        liquidity: payload,
      },
      errorMessage: `awaiting real liquidity: ${plan.blockers.map((entry) => `${entry.provider}: ${entry.blocker}`).join(' | ')}`,
    },
  });

  await prisma.transactionEvent.create({
    data: {
      transactionId: transaction.id,
      eventType: 'liquidity.awaiting_funding',
      payload,
    },
  });

  return updated;
}

module.exports = {
  buildLiquidityPlan,
  decimalToUnits,
  getProviderLiquidityState,
  markLiquidityPending,
  requiredSettlement,
  syncOnChainTreasury,
  syncStripeTreasury,
  syncWiseTreasury,
  unitsToDecimal,
};

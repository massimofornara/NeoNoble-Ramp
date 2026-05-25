function getPspAdapterName() {
  return String(process.env.PSP_ADAPTER || 'transak').toLowerCase();
}

function toMinorUnits(amount) {
  const [whole, fraction = ''] = String(amount || '0').split('.');
  return Number.parseInt(`${whole}${fraction.padEnd(2, '0').slice(0, 2)}`, 10);
}

async function postProviderPayout(url, apiKey, transaction, provider) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      transactionId: transaction.id,
      userId: transaction.userId,
      amount: transaction.fiatAmount,
      currency: transaction.fiatCurrency,
      payoutDestination: transaction.toAddress || transaction.paymentReference,
      metadata: {
        txHash: transaction.txHash,
        network: transaction.network,
      },
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${provider} payout request failed: ${response.status} ${text}`);
  }

  const payload = await response.json();
  if (!payload.id && !payload.settlementId) {
    throw new Error(`${provider} payout response missing settlement id`);
  }

  return {
    settlementId: String(payload.settlementId || payload.id),
    paymentReference: String(payload.paymentReference || payload.reference || payload.id || payload.settlementId),
    provider,
    status: String(payload.status || 'requested'),
    raw: payload,
  };
}

async function createPayoutRequest(transaction) {
  const adapter = getPspAdapterName();

  if (adapter === 'disabled') {
    throw new Error('PSP_ADAPTER=disabled; fiat settlement cannot be requested');
  }

  if (adapter === 'transak') {
    if (!process.env.TRANSAK_PAYOUT_API_URL || !process.env.TRANSAK_API_KEY) {
      throw new Error('TRANSAK_PAYOUT_API_URL and TRANSAK_API_KEY are required for Transak payout requests');
    }

    return postProviderPayout(process.env.TRANSAK_PAYOUT_API_URL, process.env.TRANSAK_API_KEY, transaction, 'transak');
  }

  if (adapter === 'stripe') {
    if (!process.env.STRIPE_SECRET_KEY) {
      throw new Error('STRIPE_SECRET_KEY is required for Stripe payout requests');
    }

    const Stripe = require('stripe');
    const stripe = new Stripe(process.env.STRIPE_SECRET_KEY);
    const payout = await stripe.payouts.create({
      amount: toMinorUnits(transaction.fiatAmount),
      currency: String(transaction.fiatCurrency || 'eur').toLowerCase(),
      metadata: {
        transactionId: transaction.id,
        userId: transaction.userId,
        txHash: transaction.txHash || '',
      },
    });

    return {
      settlementId: payout.id,
      paymentReference: payout.id,
      provider: 'stripe',
      status: payout.status,
      raw: payout,
    };
  }

  if (adapter === 'sepa') {
    if (!process.env.SEPA_PAYOUT_API_URL || !process.env.SEPA_PROVIDER_API_KEY) {
      throw new Error('SEPA_PAYOUT_API_URL and SEPA_PROVIDER_API_KEY are required for SEPA payout requests');
    }

    return postProviderPayout(process.env.SEPA_PAYOUT_API_URL, process.env.SEPA_PROVIDER_API_KEY, transaction, 'sepa');
  }

  throw new Error(`Unsupported PSP_ADAPTER: ${adapter}`);
}

module.exports = {
  createPayoutRequest,
};

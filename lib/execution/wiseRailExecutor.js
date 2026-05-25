import crypto from 'node:crypto';

function getWiseConfig() {
  return {
    baseUrl: process.env.WISE_BASE_URL || '',
    accessToken: process.env.WISE_ACCESS_TOKEN || '',
    profileId: process.env.WISE_PROFILE_ID || '',
    balanceId: process.env.WISE_BALANCE_ID || '',
    payoutsEnabled: process.env.WISE_PAYOUTS_ENABLED === 'true',
    defaultBeneficiaryName: process.env.WISE_DEFAULT_BENEFICIARY_NAME || '',
    recipientAccountId: process.env.WISE_RECIPIENT_ACCOUNT_ID || '',
  };
}

async function wiseFetch(path, init = {}) {
  const config = getWiseConfig();
  if (!config.baseUrl || !config.accessToken || !config.profileId) {
    throw new Error('WISE_BASE_URL, WISE_ACCESS_TOKEN and WISE_PROFILE_ID are required for Wise payouts');
  }

  const response = await fetch(`${config.baseUrl}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${config.accessToken}`,
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
  });
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(`Wise API ${response.status}: ${JSON.stringify(body)}`);
  }
  return body;
}

async function ensureRecipientAccount(transaction) {
  const config = getWiseConfig();
  if (config.recipientAccountId) return Number(config.recipientAccountId);
  if (!config.defaultBeneficiaryName) {
    throw new Error('WISE_DEFAULT_BENEFICIARY_NAME or WISE_RECIPIENT_ACCOUNT_ID is required for Wise IBAN payouts');
  }
  if (!transaction.paymentReference) {
    throw new Error('paymentReference must contain payout IBAN for Wise payouts');
  }

  const account = await wiseFetch('/v1/accounts', {
    method: 'POST',
    body: JSON.stringify({
      profile: Number(config.profileId),
      accountHolderName: config.defaultBeneficiaryName,
      currency: 'EUR',
      type: 'iban',
      details: {
        legalType: 'PRIVATE',
        IBAN: transaction.paymentReference,
      },
    }),
  });
  if (!account.id) throw new Error('Wise recipient account response missing id');
  return account.id;
}

export async function createWisePayoutAction(transaction) {
  const config = getWiseConfig();
  if (!config.payoutsEnabled) {
    throw new Error('WISE_PAYOUTS_ENABLED must be true for Wise payouts');
  }
  if (String(transaction.fiatCurrency || '').toUpperCase() !== 'EUR') {
    throw new Error('Wise payout executor currently supports EUR off-ramp only');
  }

  const targetAccount = await ensureRecipientAccount(transaction);
  const customerTransactionId = crypto.randomUUID();
  const amount = Number(transaction.fiatAmount);
  if (!Number.isFinite(amount) || amount <= 0) {
    throw new Error('Wise payout amount must be a positive number');
  }

  const quote = await wiseFetch(`/v3/profiles/${config.profileId}/quotes`, {
    method: 'POST',
    body: JSON.stringify({
      sourceCurrency: 'EUR',
      targetCurrency: 'EUR',
      sourceAmount: amount,
      payOut: 'BANK_TRANSFER',
      preferredPayIn: 'BALANCE',
    }),
  });
  if (!quote.id) throw new Error('Wise quote response missing id');

  const transfer = await wiseFetch('/v1/transfers', {
    method: 'POST',
    body: JSON.stringify({
      targetAccount,
      quoteUuid: quote.id,
      customerTransactionId,
      details: {
        reference: `NeoNoble ${transaction.id}`,
      },
    }),
  });
  if (!transfer.id) throw new Error('Wise transfer response missing id');

  const payment = await wiseFetch(`/v3/profiles/${config.profileId}/transfers/${transfer.id}/payments`, {
    method: 'POST',
    body: JSON.stringify({
      type: 'BALANCE',
    }),
  });

  return {
    provider: 'wise',
    type: 'balance_transfer',
    settlementId: String(transfer.id),
    payoutReference: String(transfer.id),
    status: String(payment.status || transfer.status || 'outgoing_payment_sent'),
    customerTransactionId,
    quoteId: quote.id,
    targetAccount,
    raw: {
      quote,
      transfer,
      payment,
    },
  };
}

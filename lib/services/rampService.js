import { NENO_CONFIG, FEE_RATE, SUPPORTED_TOKENS, SUPPORTED_CHAINS } from '../../config/tokens';

/**
 * Calculate onramp quote (fiat -> token)
 */
export function calculateOnrampQuote({ fromFiat, toToken, chain, amountFiat }) {
  // Validate inputs
  if (fromFiat !== 'EUR') {
    throw new Error('Only EUR is supported as fromFiat currency');
  }

  const tokenConfig = SUPPORTED_TOKENS[toToken];
  if (!tokenConfig) {
    throw new Error(`Token ${toToken} is not supported`);
  }

  if (!SUPPORTED_CHAINS.includes(chain)) {
    throw new Error(`Chain ${chain} is not supported`);
  }

  if (amountFiat <= 0) {
    throw new Error('amountFiat must be greater than 0');
  }

  // Calculate using fixed price
  const rate = tokenConfig.fixedPriceEur;
  const estimatedTokens = amountFiat / rate;
  const feeBase = amountFiat * FEE_RATE;

  return {
    amountFiat: parseFloat(amountFiat.toFixed(2)),
    estimatedTokens: parseFloat(estimatedTokens.toFixed(tokenConfig.decimals)),
    rate,
    feeBase: parseFloat(feeBase.toFixed(2)),
    token: toToken,
    chain,
  };
}

/**
 * Calculate offramp quote (token -> fiat)
 */
export function calculateOfframpQuote({ token, chain, tokens }) {
  // Validate inputs
  const tokenConfig = SUPPORTED_TOKENS[token];
  if (!tokenConfig) {
    throw new Error(`Token ${token} is not supported`);
  }

  if (!SUPPORTED_CHAINS.includes(chain)) {
    throw new Error(`Chain ${chain} is not supported`);
  }

  if (tokens <= 0) {
    throw new Error('tokens must be greater than 0');
  }

  // Calculate using fixed price
  const rate = tokenConfig.fixedPriceEur;
  const amountFiat = tokens * rate;
  const feeBase = amountFiat * FEE_RATE;

  return {
    tokens: parseFloat(tokens.toFixed(tokenConfig.decimals)),
    amountFiat: parseFloat(amountFiat.toFixed(2)),
    rate,
    feeBase: parseFloat(feeBase.toFixed(2)),
  };
}

/**
 * Generate a unique session ID
 */
export function generateSessionId() {
  const timestamp = Date.now();
  const random = Math.random().toString(36).substring(2, 10);
  return `NRAMP_${timestamp}_${random}`;
}

/**
 * Generate checkout URL for a session
 */
export function generateCheckoutUrl(sessionId, baseUrl) {
  return `${baseUrl}/ramp/checkout/${sessionId}`;
}
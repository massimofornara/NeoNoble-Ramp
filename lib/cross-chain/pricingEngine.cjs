const DEFAULT_NENO_USDT_PRICE = '1000';

function decimalToScaled(value) {
  const raw = String(value || '0');
  const [whole, fraction = ''] = raw.split('.');
  return BigInt(whole || '0') * 10n ** 18n + BigInt((fraction + '0'.repeat(18)).slice(0, 18));
}

function scaledToDecimal(value) {
  const whole = value / 10n ** 18n;
  const fraction = (value % 10n ** 18n).toString().padStart(18, '0').replace(/0+$/, '');
  return `${whole.toString()}${fraction ? `.${fraction}` : ''}`;
}

function quoteFixedNenoToUsdt(amount) {
  const price = process.env.NENO_FIXED_PRICE_USDT || DEFAULT_NENO_USDT_PRICE;
  return {
    inputAsset: 'NENO',
    outputAsset: 'USDT',
    inputAmount: String(amount),
    price,
    outputAmount: scaledToDecimal((decimalToScaled(amount) * decimalToScaled(price)) / 10n ** 18n),
    pricingModel: 'fixed_rate',
  };
}

module.exports = {
  DEFAULT_NENO_USDT_PRICE,
  quoteFixedNenoToUsdt,
};

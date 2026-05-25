const { broadcastTokenTransferOnChain, getTransactionStatusOnChain } = require('./walletService.cjs');

const NENO_FIXED_PRICE_USDT = '1000';

function multiplyDecimal(amount, price) {
  const amountText = String(amount);
  const priceText = String(price);
  const amountScale = (amountText.split('.')[1] || '').length;
  const priceScale = (priceText.split('.')[1] || '').length;
  const scale = amountScale + priceScale;
  const amountInt = BigInt(amountText.replace('.', ''));
  const priceInt = BigInt(priceText.replace('.', ''));
  const result = amountInt * priceInt;
  const divisor = 10n ** BigInt(scale);
  const whole = result / divisor;
  const fraction = result % divisor;
  const fractionText = fraction.toString().padStart(scale, '0').replace(/0+$/, '');
  return `${whole.toString()}${fractionText ? `.${fractionText}` : ''}`;
}

function calculateNenoToUsdtOutput(nenoAmount) {
  return multiplyDecimal(nenoAmount, process.env.NENO_FIXED_PRICE_USDT || NENO_FIXED_PRICE_USDT);
}

async function executeSwapOnChain(transaction) {
  const toAsset = String(transaction.toToken || '').toUpperCase();
  if (toAsset !== 'USDT') {
    throw new Error(`Only NENO -> USDT execution is currently supported, got ${transaction.fromToken} -> ${transaction.toToken}`);
  }

  const outputAmount = transaction.fiatAmount || calculateNenoToUsdtOutput(transaction.cryptoAmount);
  const toAddress = transaction.toAddress || process.env.DEFAULT_SETTLEMENT_ADDRESS;

  return broadcastTokenTransferOnChain({
    chain: transaction.chainName || transaction.network || 'BSC',
    asset: 'USDT',
    toAddress,
    amount: outputAmount,
    transactionId: transaction.id,
  });
}

async function executeOnChainPayout(transaction) {
  const payoutAsset = String(transaction.fiatCurrency || transaction.toToken || '').toUpperCase();
  const chain = transaction.chainName || transaction.network || 'BSC';

  if (payoutAsset !== 'USDT') {
    const treasuryAddress = process.env.OFFRAMP_TREASURY_ADDRESS || process.env.BURN_ADDRESS;
    if (!treasuryAddress) {
      throw new Error('OFFRAMP_TREASURY_ADDRESS or BURN_ADDRESS is required for fiat off-ramp on-chain leg');
    }

    return broadcastTokenTransferOnChain({
      chain,
      asset: transaction.fromToken || 'NENO',
      toAddress: treasuryAddress,
      amount: transaction.cryptoAmount,
      transactionId: transaction.id,
    });
  }

  const toAddress = transaction.toAddress || process.env.DEFAULT_SETTLEMENT_ADDRESS;
  return broadcastTokenTransferOnChain({
    chain,
    asset: 'USDT',
    toAddress,
    amount: transaction.fiatAmount,
    transactionId: transaction.id,
  });
}

module.exports = {
  NENO_FIXED_PRICE_USDT,
  calculateNenoToUsdtOutput,
  executeOnChainPayout,
  executeSwapOnChain,
  getTransactionChainStatus: getTransactionStatusOnChain,
};

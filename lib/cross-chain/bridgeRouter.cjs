const { getChainConfig } = require('../chains/chainConfig.cjs');
const { quoteFixedNenoToUsdt } = require('./pricingEngine.cjs');

function resolveBridgeProvider(fromChain, toChain) {
  const provider = process.env.BRIDGE_PROVIDER || 'disabled';
  if (provider === 'disabled') {
    throw new Error(`BRIDGE_PROVIDER is disabled; cannot route ${fromChain} -> ${toChain}`);
  }
  return provider;
}

function planCrossChainSwap({ fromChain, toChain, fromAsset, toAsset, amount }) {
  const source = getChainConfig(fromChain);
  const destination = getChainConfig(toChain);
  const sameChain = source.chainId === destination.chainId;
  const quote =
    String(fromAsset).toUpperCase() === 'NENO' && String(toAsset).toUpperCase() === 'USDT'
      ? quoteFixedNenoToUsdt(amount)
      : null;

  if (!quote) {
    throw new Error(`Unsupported cross-chain pair: ${fromAsset} -> ${toAsset}`);
  }

  return {
    sourceChain: source,
    destinationChain: destination,
    routeType: sameChain ? 'same_chain_settlement' : 'bridge_then_settle',
    bridgeProvider: sameChain ? null : resolveBridgeProvider(source.chainName, destination.chainName),
    quote,
    settlementLayer: destination.settlementLayer,
  };
}

module.exports = {
  planCrossChainSwap,
};

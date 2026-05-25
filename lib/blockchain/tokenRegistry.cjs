const { getChainConfig } = require('../chains/chainConfig.cjs');

const BSC_MAINNET_USDT = '0x55d398326f99059fF775485246999027B3197955';

function normalizeAsset(asset) {
  return String(asset || '').trim().toUpperCase();
}

function getTokenConfig(asset, chain = 'BSC') {
  const normalized = normalizeAsset(asset);
  const chainConfig = getChainConfig(chain);
  const token = chainConfig.tokens[normalized];

  if (!token) {
    throw new Error(`Unsupported asset ${asset} on ${chainConfig.chainName}`);
  }

  const address =
    process.env[token.addressEnv] ||
    (token.legacyAddressEnv ? process.env[token.legacyAddressEnv] : undefined) ||
    (normalized === 'USDT' ? process.env.USDT_CONTRACT_ADDRESS : undefined) ||
    token.fallbackAddress;

  if (!address) {
    throw new Error(`${token.addressEnv} is required for ${normalized} on ${chainConfig.chainName}`);
  }

  return {
    symbol: normalized,
    address,
    decimals: Number.parseInt(process.env[token.decimalsEnv] || String(token.fallbackDecimals), 10),
    chainId: chainConfig.chainId,
    chainName: chainConfig.chainName,
    settlementLayer: chainConfig.settlementLayer,
  };
}

module.exports = {
  BSC_MAINNET_USDT,
  getTokenConfig,
  normalizeAsset,
};

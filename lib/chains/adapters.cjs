const { getChainConfig } = require('./chainConfig.cjs');
const { EVMChainAdapter } = require('./evmAdapter.cjs');

class BSCAdapter extends EVMChainAdapter {
  constructor() {
    super(getChainConfig('BSC'));
  }
}

class EthereumAdapter extends EVMChainAdapter {
  constructor() {
    super(getChainConfig('ETHEREUM'));
  }
}

class L2Adapter extends EVMChainAdapter {
  constructor(chain) {
    super(getChainConfig(chain));
  }
}

const adapterCache = new Map();

function getChainAdapter(chain = 'BSC') {
  const config = getChainConfig(chain);
  if (!adapterCache.has(config.key)) {
    if (config.key === 'BSC') adapterCache.set(config.key, new BSCAdapter());
    else if (config.key === 'ETHEREUM') adapterCache.set(config.key, new EthereumAdapter());
    else adapterCache.set(config.key, new L2Adapter(config.key));
  }
  return adapterCache.get(config.key);
}

function listImplementedAdapters() {
  return [
    { name: 'BSCAdapter', chainId: 56, chainName: 'BSC' },
    { name: 'EthereumAdapter', chainId: 1, chainName: 'Ethereum' },
    { name: 'L2Adapter', chainId: 42161, chainName: 'Arbitrum' },
    { name: 'L2Adapter', chainId: 10, chainName: 'Optimism' },
    { name: 'L2Adapter', chainId: 324, chainName: 'zkSync' },
  ];
}

module.exports = {
  BSCAdapter,
  EthereumAdapter,
  L2Adapter,
  getChainAdapter,
  listImplementedAdapters,
};

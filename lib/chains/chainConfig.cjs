const CHAIN_CONFIGS = {
  BSC: {
    key: 'BSC',
    chainId: 56,
    chainName: 'BSC',
    settlementLayer: 'bsc',
    rpcEnv: 'BSC_RPC_URL',
    confirmationsEnv: 'BSC_CONFIRMATIONS',
    finalityEnv: 'BSC_FINALITY_CONFIRMATIONS',
    defaultRpcUrl: 'https://bsc-dataseed1.binance.org/',
    tokens: {
      USDT: {
        addressEnv: 'BSC_USDT_CONTRACT_ADDRESS',
        fallbackAddress: '0x55d398326f99059fF775485246999027B3197955',
        decimalsEnv: 'BSC_USDT_DECIMALS',
        fallbackDecimals: 18,
      },
      NENO: {
        addressEnv: 'BSC_NENO_CONTRACT_ADDRESS',
        legacyAddressEnv: 'NENO_CONTRACT_ADDRESS',
        decimalsEnv: 'BSC_NENO_DECIMALS',
        fallbackDecimals: 18,
      },
    },
  },
  ETHEREUM: {
    key: 'ETHEREUM',
    chainId: 1,
    chainName: 'Ethereum',
    settlementLayer: 'ethereum',
    rpcEnv: 'ETHEREUM_RPC_URL',
    confirmationsEnv: 'ETHEREUM_CONFIRMATIONS',
    finalityEnv: 'ETHEREUM_FINALITY_CONFIRMATIONS',
    defaultRpcUrl: '',
    tokens: {
      USDT: {
        addressEnv: 'ETHEREUM_USDT_CONTRACT_ADDRESS',
        fallbackAddress: '0xdAC17F958D2ee523a2206206994597C13D831ec7',
        decimalsEnv: 'ETHEREUM_USDT_DECIMALS',
        fallbackDecimals: 6,
      },
      NENO: {
        addressEnv: 'ETHEREUM_NENO_CONTRACT_ADDRESS',
        decimalsEnv: 'ETHEREUM_NENO_DECIMALS',
        fallbackDecimals: 18,
      },
    },
  },
  ARBITRUM: {
    key: 'ARBITRUM',
    chainId: 42161,
    chainName: 'Arbitrum',
    settlementLayer: 'arbitrum',
    rpcEnv: 'ARBITRUM_RPC_URL',
    confirmationsEnv: 'ARBITRUM_CONFIRMATIONS',
    finalityEnv: 'ARBITRUM_FINALITY_CONFIRMATIONS',
    defaultRpcUrl: '',
    tokens: {
      USDT: {
        addressEnv: 'ARBITRUM_USDT_CONTRACT_ADDRESS',
        fallbackAddress: '0xFd086bC7CD5C481DCC9C85ebe478A1C0b69FCbb9',
        decimalsEnv: 'ARBITRUM_USDT_DECIMALS',
        fallbackDecimals: 6,
      },
      NENO: {
        addressEnv: 'ARBITRUM_NENO_CONTRACT_ADDRESS',
        decimalsEnv: 'ARBITRUM_NENO_DECIMALS',
        fallbackDecimals: 18,
      },
    },
  },
  OPTIMISM: {
    key: 'OPTIMISM',
    chainId: 10,
    chainName: 'Optimism',
    settlementLayer: 'optimism',
    rpcEnv: 'OPTIMISM_RPC_URL',
    confirmationsEnv: 'OPTIMISM_CONFIRMATIONS',
    finalityEnv: 'OPTIMISM_FINALITY_CONFIRMATIONS',
    defaultRpcUrl: '',
    tokens: {
      USDT: {
        addressEnv: 'OPTIMISM_USDT_CONTRACT_ADDRESS',
        fallbackAddress: '0x94b008aD8eD6f92FBe2d8ccfEEac927960287cF4',
        decimalsEnv: 'OPTIMISM_USDT_DECIMALS',
        fallbackDecimals: 6,
      },
      NENO: {
        addressEnv: 'OPTIMISM_NENO_CONTRACT_ADDRESS',
        decimalsEnv: 'OPTIMISM_NENO_DECIMALS',
        fallbackDecimals: 18,
      },
    },
  },
  ZKSYNC: {
    key: 'ZKSYNC',
    chainId: 324,
    chainName: 'zkSync',
    settlementLayer: 'zksync',
    rpcEnv: 'ZKSYNC_RPC_URL',
    confirmationsEnv: 'ZKSYNC_CONFIRMATIONS',
    finalityEnv: 'ZKSYNC_FINALITY_CONFIRMATIONS',
    defaultRpcUrl: '',
    tokens: {
      USDT: {
        addressEnv: 'ZKSYNC_USDT_CONTRACT_ADDRESS',
        fallbackAddress: '0x493257fD37EDB34451f62EDf8D2a0C418852bA4C',
        decimalsEnv: 'ZKSYNC_USDT_DECIMALS',
        fallbackDecimals: 6,
      },
      NENO: {
        addressEnv: 'ZKSYNC_NENO_CONTRACT_ADDRESS',
        decimalsEnv: 'ZKSYNC_NENO_DECIMALS',
        fallbackDecimals: 18,
      },
    },
  },
};

function normalizeChainKey(chain) {
  const raw = String(chain || 'BSC').trim().toUpperCase();
  if (raw === 'ETH' || raw === 'MAINNET' || raw === 'ETHEREUM_MAINNET') return 'ETHEREUM';
  if (raw === 'ARB') return 'ARBITRUM';
  if (raw === 'OP') return 'OPTIMISM';
  if (raw === 'ZK' || raw === 'ZKSYNCERA' || raw === 'ZKSYNC_ERA') return 'ZKSYNC';
  return raw;
}

function getChainConfig(chain) {
  const key = normalizeChainKey(chain);
  const config = CHAIN_CONFIGS[key];
  if (!config) {
    throw new Error(`Unsupported chain: ${chain}`);
  }
  return config;
}

function getChainById(chainId) {
  const id = Number(chainId || 56);
  const config = Object.values(CHAIN_CONFIGS).find((item) => item.chainId === id);
  if (!config) {
    throw new Error(`Unsupported chainId: ${chainId}`);
  }
  return config;
}

module.exports = {
  CHAIN_CONFIGS,
  getChainById,
  getChainConfig,
  normalizeChainKey,
};

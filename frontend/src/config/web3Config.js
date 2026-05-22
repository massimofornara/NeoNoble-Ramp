/**
 * Web3 Configuration for NeoNoble Ramp
 * Supports: MetaMask, WalletConnect, Coinbase Wallet, Trust Wallet
 */

import { http, createConfig } from 'wagmi';
import { mainnet, bsc, polygon, arbitrum, base, sepolia } from 'wagmi/chains';
import { coinbaseWallet, injected } from 'wagmi/connectors';

// Supported chains
export const supportedChains = [mainnet, bsc, polygon, arbitrum, base, sepolia];

// Chain metadata for display
export const chainMetadata = {
  1: { name: 'Ethereum', symbol: 'ETH', icon: '⟠', color: '#627EEA' },
  56: { name: 'BNB Smart Chain', symbol: 'BNB', icon: '🔶', color: '#F3BA2F' },
  137: { name: 'Polygon', symbol: 'MATIC', icon: '🟣', color: '#8247E5' },
  42161: { name: 'Arbitrum', symbol: 'ETH', icon: '🔵', color: '#28A0F0' },
  8453: { name: 'Base', symbol: 'ETH', icon: '🔷', color: '#0052FF' },
  11155111: { name: 'Sepolia', symbol: 'ETH', icon: '🧪', color: '#CFB5F0' },
};

// Build connectors list — only add WalletConnect if valid project ID exists
const connectors = [
  injected({ shimDisconnect: true }),
  coinbaseWallet({ appName: 'NeoNoble Ramp' }),
];

const wcProjectId = process.env.REACT_APP_WALLETCONNECT_PROJECT_ID;
if (wcProjectId && wcProjectId !== 'demo-project-id' && wcProjectId.length > 10) {
  // Only import and add WalletConnect if a real project ID is configured
  const { walletConnect } = require('wagmi/connectors');
  connectors.push(walletConnect({
    projectId: wcProjectId,
    showQrModal: true,
    metadata: {
      name: 'NeoNoble Ramp',
      description: 'Enterprise Fintech Infrastructure - Crypto On/Off Ramp',
      url: 'https://neonobleramp.com',
      icons: ['https://neonobleramp.com/logo.png'],
    },
  }));
}

// Wagmi configuration
export const wagmiConfig = createConfig({
  chains: supportedChains,
  connectors,
  transports: {
    [mainnet.id]: http(),
    [bsc.id]: http('https://bsc-dataseed1.binance.org'),
    [polygon.id]: http('https://polygon-rpc.com'),
    [arbitrum.id]: http('https://arb1.arbitrum.io/rpc'),
    [base.id]: http('https://mainnet.base.org'),
    [sepolia.id]: http(),
  },
});

// Wallet metadata for UI — only show WalletConnect if configured
const wcAvailable = !!(process.env.REACT_APP_WALLETCONNECT_PROJECT_ID && process.env.REACT_APP_WALLETCONNECT_PROJECT_ID !== 'demo-project-id');

export const walletMetadata = [
  {
    id: 'metamask',
    name: 'MetaMask',
    icon: '🦊',
    description: 'Connect using MetaMask browser extension',
    connector: 'injected',
  },
  ...(wcAvailable ? [{
    id: 'walletconnect',
    name: 'WalletConnect',
    icon: '🔗',
    description: 'Scan QR code with any WalletConnect wallet',
    connector: 'walletConnect',
  }] : []),
  {
    id: 'coinbase',
    name: 'Coinbase Wallet',
    icon: '🔵',
    description: 'Connect using Coinbase Wallet',
    connector: 'coinbaseWallet',
  },
  ...(wcAvailable ? [{
    id: 'trust',
    name: 'Trust Wallet',
    icon: '🛡️',
    description: 'Connect via WalletConnect or browser',
    connector: 'walletConnect',
  }] : []),
];

export default wagmiConfig;

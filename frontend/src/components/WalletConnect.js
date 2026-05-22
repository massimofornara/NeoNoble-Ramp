/**
 * Wallet Connect Component
 * Multi-wallet support: MetaMask, WalletConnect, Coinbase Wallet, Trust Wallet
 */

import React, { useState } from 'react';
import { useWeb3 } from '../context/Web3Context';
import { walletMetadata } from '../config/web3Config';
import {
  Wallet,
  LogOut,
  ChevronDown,
  Copy,
  ExternalLink,
  Check,
  AlertCircle,
  Loader2
} from 'lucide-react';

// Wallet Icons Component
const WalletIcon = ({ wallet, size = 24 }) => {
  const icons = {
    metamask: (
      <svg width={size} height={size} viewBox="0 0 35 33" fill="none">
        <path d="M32.9 1L19.4 11l2.5-5.9L32.9 1z" fill="#E2761B" stroke="#E2761B" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M2.1 1l13.4 10.1-2.4-5.9L2.1 1zM28.2 23.5l-3.6 5.5 7.7 2.1 2.2-7.5-6.3-.1zM.8 23.6l2.2 7.5 7.7-2.1-3.6-5.5-6.3.1z" fill="#E4761B" stroke="#E4761B" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M10.4 14.5L8.3 17.7l7.6.3-.3-8.2-5.2 4.7zM24.6 14.5l-5.3-4.8-.2 8.3 7.6-.3-2.1-3.2zM10.7 29l4.6-2.2-4-3.1-.6 5.3zM19.7 26.8l4.6 2.2-.6-5.3-4 3.1z" fill="#E4761B" stroke="#E4761B" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
    walletconnect: (
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
        <path d="M9.6 11.2c3.5-3.5 9.3-3.5 12.8 0l.4.4c.2.2.2.5 0 .6l-1.4 1.4c-.1.1-.2.1-.3 0l-.6-.6c-2.5-2.5-6.5-2.5-9 0l-.6.6c-.1.1-.2.1-.3 0l-1.4-1.4c-.2-.2-.2-.5 0-.6l.4-.4zm15.8 3l1.3 1.3c.2.2.2.5 0 .6l-5.6 5.6c-.2.2-.5.2-.6 0l-4-4c0-.1-.1-.1-.2 0l-4 4c-.2.2-.5.2-.6 0l-5.6-5.6c-.2-.2-.2-.5 0-.6l1.3-1.3c.2-.2.5-.2.6 0l4 4c.1.1.1.1.2 0l4-4c.2-.2.5-.2.6 0l4 4c0 .1.1.1.2 0l4-4c.2-.2.5-.2.7 0z" fill="#3B99FC"/>
      </svg>
    ),
    coinbase: (
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
        <circle cx="16" cy="16" r="16" fill="#0052FF"/>
        <path d="M16 6c5.5 0 10 4.5 10 10s-4.5 10-10 10S6 21.5 6 16 10.5 6 16 6zm-3.5 7.5v5h2v-2h3v2h2v-5c0-1.1-.9-2-2-2h-3c-1.1 0-2 .9-2 2zm2 1h3v1h-3v-1z" fill="white"/>
      </svg>
    ),
    trust: (
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
        <path d="M16 2L4 7v9c0 7.7 5.1 14.9 12 17 6.9-2.1 12-9.3 12-17V7L16 2z" fill="#0500FF"/>
        <path d="M16 6l-8 3.5v6c0 5.4 3.4 10.4 8 11.9 4.6-1.5 8-6.5 8-11.9v-6L16 6z" fill="white"/>
        <path d="M16 10c-2.8 0-5 2.2-5 5s2.2 5 5 5 5-2.2 5-5-2.2-5-5-5zm0 8c-1.7 0-3-1.3-3-3s1.3-3 3-3 3 1.3 3 3-1.3 3-3 3z" fill="#0500FF"/>
      </svg>
    ),
  };
  return icons[wallet] || <Wallet size={size} />;
};

// Main Wallet Connect Button
export function WalletConnectButton({ className = '' }) {
  const {
    address,
    isConnected,
    isConnecting,
    currentChain,
    balance,
    openWalletModal,
    disconnectWallet,
    formatAddress,
  } = useWeb3();

  const [showDropdown, setShowDropdown] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyAddress = () => {
    if (address) {
      navigator.clipboard.writeText(address);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (isConnecting) {
    return (
      <button
        className={`flex items-center gap-2 px-4 py-2 bg-purple-500/20 text-purple-400 rounded-lg ${className}`}
        disabled
      >
        <Loader2 className="w-4 h-4 animate-spin" />
        Connessione...
      </button>
    );
  }

  if (isConnected && address) {
    return (
      <div className="relative">
        <button
          onClick={() => setShowDropdown(!showDropdown)}
          className={`flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg border border-gray-700 transition-colors ${className}`}
          data-testid="wallet-connected-btn"
        >
          <span className="text-lg">{currentChain.icon}</span>
          <span className="font-mono text-sm">{formatAddress(address)}</span>
          {balance && (
            <span className="text-gray-400 text-sm">
              {parseFloat(balance.formatted).toFixed(4)} {balance.symbol}
            </span>
          )}
          <ChevronDown className="w-4 h-4 text-gray-400" />
        </button>

        {showDropdown && (
          <div className="absolute right-0 mt-2 w-64 bg-gray-800 border border-gray-700 rounded-xl shadow-xl z-50">
            <div className="p-4 border-b border-gray-700">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">{currentChain.icon}</span>
                <span className="text-white font-medium">{currentChain.name}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-gray-400 font-mono text-sm">{formatAddress(address)}</span>
                <button
                  onClick={copyAddress}
                  className="p-1 hover:bg-gray-700 rounded"
                >
                  {copied ? (
                    <Check className="w-4 h-4 text-green-400" />
                  ) : (
                    <Copy className="w-4 h-4 text-gray-400" />
                  )}
                </button>
              </div>
            </div>
            
            {balance && (
              <div className="p-4 border-b border-gray-700">
                <span className="text-gray-400 text-sm">Saldo</span>
                <div className="text-white font-bold text-lg">
                  {parseFloat(balance.formatted).toFixed(4)} {balance.symbol}
                </div>
              </div>
            )}

            <div className="p-2">
              <a
                href={`https://bscscan.com/address/${address}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 w-full px-3 py-2 text-gray-300 hover:bg-gray-700 rounded-lg transition-colors"
              >
                <ExternalLink className="w-4 h-4" />
                Visualizza su Explorer
              </a>
              <button
                onClick={() => {
                  disconnectWallet();
                  setShowDropdown(false);
                }}
                className="flex items-center gap-2 w-full px-3 py-2 text-red-400 hover:bg-gray-700 rounded-lg transition-colors"
                data-testid="disconnect-wallet-btn"
              >
                <LogOut className="w-4 h-4" />
                Disconnetti Wallet
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <button
      onClick={openWalletModal}
      className={`flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white rounded-lg font-medium transition-all shadow-lg shadow-purple-500/25 ${className}`}
      data-testid="connect-wallet-btn"
    >
      <Wallet className="w-4 h-4" />
      Connetti Wallet
    </button>
  );
}

// Wallet Selection Modal
export function WalletModal() {
  const {
    isModalOpen,
    closeWalletModal,
    connectWallet,
    connectors,
    isConnecting,
    error,
  } = useWeb3();

  if (!isModalOpen) return null;

  const handleConnect = (connectorId) => {
    connectWallet(connectorId);
    closeWalletModal();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={closeWalletModal}
      />

      {/* Modal */}
      <div className="relative bg-gray-900 border border-gray-800 rounded-2xl w-full max-w-md mx-4 shadow-2xl">
        {/* Header */}
        <div className="p-6 border-b border-gray-800">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-bold text-white">Connetti Wallet</h2>
            <button
              onClick={closeWalletModal}
              className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
            >
              <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <p className="text-gray-400 text-sm mt-1">
            Seleziona il tuo wallet preferito
          </p>
        </div>

        {/* Error Message */}
        {error && (
          <div className="mx-6 mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-400" />
            <span className="text-red-400 text-sm">{error}</span>
          </div>
        )}

        {/* Wallet Options */}
        <div className="p-6 space-y-3">
          {walletMetadata.map((wallet) => (
            <button
              key={wallet.id}
              onClick={() => handleConnect(wallet.connector)}
              disabled={isConnecting}
              className="w-full flex items-center gap-4 p-4 bg-gray-800/50 hover:bg-gray-800 border border-gray-700 hover:border-purple-500/50 rounded-xl transition-all group disabled:opacity-50"
              data-testid={`wallet-option-${wallet.id}`}
            >
              <div className="w-12 h-12 flex items-center justify-center bg-gray-700 rounded-xl group-hover:bg-gray-600 transition-colors">
                <WalletIcon wallet={wallet.id} size={28} />
              </div>
              <div className="flex-1 text-left">
                <div className="text-white font-medium">{wallet.name}</div>
                <div className="text-gray-400 text-sm">{wallet.description}</div>
              </div>
              {isConnecting && (
                <Loader2 className="w-5 h-5 text-purple-400 animate-spin" />
              )}
            </button>
          ))}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-800">
          <p className="text-gray-500 text-xs text-center">
            Connettendo il tuo wallet, accetti i{' '}
            <a href="#" className="text-purple-400 hover:underline">Termini di Servizio</a>
            {' '}e la{' '}
            <a href="#" className="text-purple-400 hover:underline">Privacy Policy</a>
          </p>
        </div>
      </div>
    </div>
  );
}

// Chain Selector Component
export function ChainSelector() {
  const { chainId, currentChain, changeChain, chainMetadata, isConnected } = useWeb3();
  const [showDropdown, setShowDropdown] = useState(false);

  if (!isConnected) return null;

  const chains = Object.entries(chainMetadata);

  return (
    <div className="relative">
      <button
        onClick={() => setShowDropdown(!showDropdown)}
        className="flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg border border-gray-700 transition-colors"
        data-testid="chain-selector-btn"
      >
        <span className="text-lg">{currentChain.icon}</span>
        <span className="text-white text-sm">{currentChain.name}</span>
        <ChevronDown className="w-4 h-4 text-gray-400" />
      </button>

      {showDropdown && (
        <div className="absolute right-0 mt-2 w-56 bg-gray-800 border border-gray-700 rounded-xl shadow-xl z-50">
          <div className="p-2">
            <div className="px-3 py-2 text-gray-400 text-xs font-medium uppercase">
              Seleziona Chain
            </div>
            {chains.map(([id, chain]) => (
              <button
                key={id}
                onClick={() => {
                  changeChain(parseInt(id));
                  setShowDropdown(false);
                }}
                className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg transition-colors ${
                  chainId === parseInt(id)
                    ? 'bg-purple-500/20 text-purple-400'
                    : 'text-gray-300 hover:bg-gray-700'
                }`}
              >
                <span className="text-lg">{chain.icon}</span>
                <span>{chain.name}</span>
                {chainId === parseInt(id) && (
                  <Check className="w-4 h-4 ml-auto" />
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default WalletConnectButton;

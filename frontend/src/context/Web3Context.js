/**
 * Web3 Context Provider for NeoNoble Ramp
 * Manages wallet connections + real NENO token balance + transaction signing
 */

import React, { createContext, useContext, useState, useCallback } from 'react';
import {
  WagmiProvider,
  useAccount,
  useConnect,
  useDisconnect,
  useBalance,
  useChainId,
  useSwitchChain,
  useReadContract,
  useWriteContract,
  useWaitForTransactionReceipt,
} from 'wagmi';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { wagmiConfig, chainMetadata, supportedChains } from '../config/web3Config';
import { NENO_CONTRACT_ADDRESS, NENO_ABI, NENO_DECIMALS, BSC_CHAIN_ID } from '../config/nenoContract';
import { parseUnits, formatUnits } from 'viem';

const queryClient = new QueryClient();
const Web3Context = createContext(null);

function Web3ContextInner({ children }) {
  const { address, isConnected, isConnecting, connector } = useAccount();
  const { connect, connectors, isPending, error: connectError } = useConnect();
  const { disconnect } = useDisconnect();
  const chainId = useChainId();
  const { switchChain } = useSwitchChain();

  const { data: balance } = useBalance({ address, watch: true });

  // Real on-chain NENO token balance (BSC)
  const { data: nenoRawBalance, refetch: refetchNenoBalance } = useReadContract({
    address: NENO_CONTRACT_ADDRESS,
    abi: NENO_ABI,
    functionName: 'balanceOf',
    args: address ? [address] : undefined,
    chainId: BSC_CHAIN_ID,
    query: { enabled: !!address },
  });

  const nenoOnChainBalance = nenoRawBalance
    ? parseFloat(formatUnits(nenoRawBalance, NENO_DECIMALS))
    : 0;

  // Transaction signing via writeContract
  const {
    writeContractAsync,
    data: txHash,
    isPending: isTxPending,
    error: txError,
    reset: resetTx,
  } = useWriteContract();

  // Wait for tx receipt
  const { data: txReceipt, isLoading: isWaitingReceipt } = useWaitForTransactionReceipt({
    hash: txHash,
    chainId: BSC_CHAIN_ID,
  });

  const [walletState, setWalletState] = useState({ isModalOpen: false, error: null });
  const currentChain = chainMetadata[chainId] || { name: 'Unknown', symbol: '?', icon: '?' };

  /**
   * Transfer NENO tokens on-chain to a recipient address.
   * Returns the tx hash on success.
   */
  const transferNeno = useCallback(async (toAddress, amountFloat) => {
    if (!address) throw new Error('Wallet non connesso');
    if (chainId !== BSC_CHAIN_ID) {
      if (switchChain) switchChain({ chainId: BSC_CHAIN_ID });
      throw new Error('Per favore passa alla BSC Mainnet (chain 56) nel tuo wallet');
    }
    const amountWei = parseUnits(String(amountFloat), NENO_DECIMALS);
    const hash = await writeContractAsync({
      address: NENO_CONTRACT_ADDRESS,
      abi: NENO_ABI,
      functionName: 'transfer',
      args: [toAddress, amountWei],
      chainId: BSC_CHAIN_ID,
    });
    return hash;
  }, [address, chainId, switchChain, writeContractAsync]);

  const connectWallet = useCallback(async (connectorId) => {
    try {
      setWalletState(prev => ({ ...prev, error: null }));
      const selectedConnector = connectors.find(c =>
        c.id === connectorId || c.name.toLowerCase().includes(connectorId.toLowerCase())
      );
      connect({ connector: selectedConnector || connectors[0] });
    } catch (err) {
      setWalletState(prev => ({ ...prev, error: err.message }));
    }
  }, [connect, connectors]);

  const disconnectWallet = useCallback(() => {
    disconnect();
    setWalletState(prev => ({ ...prev, error: null }));
  }, [disconnect]);

  const changeChain = useCallback(async (newChainId) => {
    try {
      if (switchChain) switchChain({ chainId: newChainId });
    } catch (err) {
      setWalletState(prev => ({ ...prev, error: err.message }));
    }
  }, [switchChain]);

  const openWalletModal = () => setWalletState(prev => ({ ...prev, isModalOpen: true }));
  const closeWalletModal = () => setWalletState(prev => ({ ...prev, isModalOpen: false }));
  const formatAddress = (addr) => addr ? `${addr.slice(0, 6)}...${addr.slice(-4)}` : '';

  const value = {
    address, isConnected, isConnecting: isConnecting || isPending, connector,
    chainId, currentChain, supportedChains, chainMetadata,
    balance: balance ? { value: balance.value, formatted: balance.formatted, symbol: balance.symbol } : null,
    // NENO on-chain
    nenoOnChainBalance,
    refetchNenoBalance,
    // Transaction signing
    transferNeno,
    txHash,
    txReceipt,
    isTxPending,
    isWaitingReceipt,
    txError,
    resetTx,
    // Actions
    connectWallet, disconnectWallet, changeChain,
    isModalOpen: walletState.isModalOpen, openWalletModal, closeWalletModal,
    connectors,
    error: walletState.error || connectError?.message,
    formatAddress,
  };

  return <Web3Context.Provider value={value}>{children}</Web3Context.Provider>;
}

export function Web3Provider({ children }) {
  return (
    <WagmiProvider config={wagmiConfig}>
      <QueryClientProvider client={queryClient}>
        <Web3ContextInner>{children}</Web3ContextInner>
      </QueryClientProvider>
    </WagmiProvider>
  );
}

export function useWeb3() {
  const context = useContext(Web3Context);
  if (!context) throw new Error('useWeb3 must be used within a Web3Provider');
  return context;
}

export default Web3Provider;

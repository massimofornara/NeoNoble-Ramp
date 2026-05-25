const { ethers } = require('ethers');
const { getChainAdapter } = require('../chains/adapters.cjs');
const { getTokenConfig } = require('./tokenRegistry.cjs');

const ERC20_ABI = [
  'function transfer(address to, uint256 value) returns (bool)',
  'function balanceOf(address account) view returns (uint256)',
  'function decimals() view returns (uint8)',
  'event Transfer(address indexed from, address indexed to, uint256 value)',
];

let providerIndex = 0;
let providerCache;
let signerCache;

function getRpcUrls() {
  return String(process.env.BSC_RPC_URL || process.env.BSC_RPC_URLS || 'https://bsc-dataseed1.binance.org/')
    .split(',')
    .map((url) => url.trim())
    .filter(Boolean);
}

function getProvider() {
  const rpcUrls = getRpcUrls();
  if (rpcUrls.length === 0) {
    throw new Error('BSC_RPC_URL is required');
  }

  if (!providerCache) {
    providerCache = new ethers.JsonRpcProvider(rpcUrls[providerIndex], Number(process.env.BSC_CHAIN_ID || 56));
  }

  return providerCache;
}

async function rotateProvider() {
  const rpcUrls = getRpcUrls();
  providerIndex = (providerIndex + 1) % rpcUrls.length;
  providerCache = new ethers.JsonRpcProvider(rpcUrls[providerIndex], Number(process.env.BSC_CHAIN_ID || 56));
  return providerCache;
}

function getPrivateKey() {
  const privateKey = process.env.HOT_WALLET_PRIVATE_KEY || process.env.BSC_PRIVATE_KEY;
  if (!privateKey) {
    throw new Error('HOT_WALLET_PRIVATE_KEY or BSC_PRIVATE_KEY is required for real signing');
  }
  return privateKey;
}

function getSigner() {
  if (!signerCache) {
    const wallet = new ethers.Wallet(getPrivateKey(), getProvider());
    signerCache = new ethers.NonceManager(wallet);
  }

  return signerCache;
}

async function getHotWalletAddress() {
  return getSigner().getAddress();
}

async function getHotWalletAddressForChain(chain = 'BSC') {
  return getChainAdapter(chain).getHotWalletAddress();
}

function requireRealExecutionMode() {
  if (process.env.BLOCKCHAIN_EXECUTION_MODE !== 'real') {
    throw new Error('BLOCKCHAIN_EXECUTION_MODE must be set to real; simulated execution is disabled');
  }
}

function validateAddress(address, fieldName = 'address') {
  if (!address || !ethers.isAddress(address)) {
    throw new Error(`${fieldName} must be a valid EVM address`);
  }
  return ethers.getAddress(address);
}

async function getTokenBalance(asset, address) {
  const token = getTokenConfig(asset);
  const checkedAddress = validateAddress(address);
  const contract = new ethers.Contract(token.address, ERC20_ABI, getProvider());
  const balance = await contract.balanceOf(checkedAddress);
  return ethers.formatUnits(balance, token.decimals);
}

async function getNativeBalance(address) {
  const checkedAddress = validateAddress(address);
  const balance = await getProvider().getBalance(checkedAddress);
  return ethers.formatEther(balance);
}

async function broadcastTokenTransfer({ asset, toAddress, amount, transactionId }) {
  requireRealExecutionMode();

  const token = getTokenConfig(asset);
  const recipient = validateAddress(toAddress, 'toAddress');
  const signer = getSigner();
  const fromAddress = await signer.getAddress();
  const contract = new ethers.Contract(token.address, ERC20_ABI, signer);
  const units = ethers.parseUnits(String(amount), token.decimals);

  if (units <= 0n) {
    throw new Error('Transfer amount must be greater than zero');
  }

  const balance = await contract.balanceOf(fromAddress);
  if (balance < units) {
    throw new Error(`Insufficient ${token.symbol} hot-wallet balance`);
  }

  const feeData = await getProvider().getFeeData();
  const overrides = {};
  if (feeData.gasPrice) {
    overrides.gasPrice = feeData.gasPrice;
  }

  const tx = await contract.transfer(recipient, units, overrides);

  return {
    txHash: tx.hash,
    fromAddress,
    toAddress: recipient,
    rawTxData: {
      hash: tx.hash,
      nonce: tx.nonce,
      chainId: tx.chainId ? tx.chainId.toString() : String(process.env.BSC_CHAIN_ID || 56),
      from: tx.from,
      to: tx.to,
      data: tx.data,
      value: tx.value ? tx.value.toString() : '0',
      gasLimit: tx.gasLimit ? tx.gasLimit.toString() : undefined,
      gasPrice: tx.gasPrice ? tx.gasPrice.toString() : undefined,
      transactionId,
      asset: token.symbol,
      tokenAddress: token.address,
      amount: String(amount),
    },
  };
}

async function broadcastTokenTransferOnChain({ chain = 'BSC', asset, toAddress, amount, transactionId }) {
  return getChainAdapter(chain).broadcastTokenTransfer({ asset, toAddress, amount, transactionId });
}

async function getTransactionChainStatus(txHash) {
  const provider = getProvider();
  const tx = await provider.getTransaction(txHash);
  const receipt = await provider.getTransactionReceipt(txHash);
  const currentBlock = await provider.getBlockNumber();

  if (!receipt) {
    return {
      txHash,
      chainStatus: tx ? 'pending' : 'not_found',
      confirmations: 0,
      blockNumber: null,
      gasUsed: null,
      receiptStatus: null,
    };
  }

  const confirmations = Math.max(currentBlock - receipt.blockNumber + 1, 0);
  const finalityThreshold = Number.parseInt(process.env.BSC_FINALITY_CONFIRMATIONS || '12', 10);
  const chainStatus =
    receipt.status === 0
      ? 'failed'
      : confirmations >= finalityThreshold
        ? 'finalized'
        : confirmations >= Number.parseInt(process.env.BSC_CONFIRMATIONS || '3', 10)
          ? 'confirmed'
          : 'included';

  return {
    txHash,
    chainStatus,
    confirmations,
    blockNumber: receipt.blockNumber,
    gasUsed: receipt.gasUsed.toString(),
    receiptStatus: receipt.status,
  };
}

async function getTransactionStatusOnChain(txHash, chain = 'BSC') {
  return getChainAdapter(chain).getTransactionStatus(txHash);
}

module.exports = {
  ERC20_ABI,
  broadcastTokenTransfer,
  broadcastTokenTransferOnChain,
  getHotWalletAddress,
  getHotWalletAddressForChain,
  getNativeBalance,
  getProvider,
  getSigner,
  getTokenBalance,
  getTransactionChainStatus,
  getTransactionStatusOnChain,
  rotateProvider,
  validateAddress,
};

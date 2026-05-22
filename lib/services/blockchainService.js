import { ethers } from 'ethers';
import { prisma } from '../prisma';

const BSC_RPC_URLS = (process.env.BSC_RPC_URL || 'https://bsc-dataseed1.binance.org/').split(',');
const BSC_PRIVATE_KEY = process.env.BSC_PRIVATE_KEY;
const NENO_CONTRACT_ADDRESS = process.env.NENO_CONTRACT_ADDRESS;
const BSC_CONFIRMATIONS = parseInt(process.env.BSC_CONFIRMATIONS || '12', 10);
const MIN_CONFIRMATIONS_THRESHOLD = parseInt(process.env.MIN_CONFIRMATIONS_THRESHOLD || '3', 10);
const DRY_RUN_MODE = process.env.DRY_RUN_MODE === 'true';
const GAS_PRICE_MULTIPLIER = parseFloat(process.env.GAS_PRICE_MULTIPLIER || '1.1');
const MAX_GAS_PRICE_GWEI = parseFloat(process.env.MAX_GAS_PRICE_GWEI || '10');

// ERC-20 ABI (minimal - only what we need)
const ERC20_ABI = [
  'function transfer(address to, uint256 amount) returns (bool)',
  'function balanceOf(address account) view returns (uint256)',
  'function decimals() view returns (uint8)',
  'event Transfer(address indexed from, address indexed to, uint256 value)',
];

let providers = [];
let currentProviderIndex = 0;
let wallet = null;
let nenoContract = null;
let nonceCache = null;

/**
 * Initialize blockchain connection with fallback providers
 */
function initializeBlockchain() {
  if (!BSC_PRIVATE_KEY || !NENO_CONTRACT_ADDRESS) {
    console.warn('⚠️  Blockchain not configured - BSC_PRIVATE_KEY or NENO_CONTRACT_ADDRESS missing');
    return false;
  }

  try {
    // Initialize multiple providers for fallback
    providers = BSC_RPC_URLS.map(url => {
      const provider = new ethers.JsonRpcProvider(url.trim());
      return provider;
    });

    if (providers.length === 0) {
      throw new Error('No RPC providers configured');
    }

    // Use first provider by default
    const primaryProvider = providers[0];
    wallet = new ethers.Wallet(BSC_PRIVATE_KEY, primaryProvider);
    nenoContract = new ethers.Contract(NENO_CONTRACT_ADDRESS, ERC20_ABI, wallet);
    
    console.log('✅ Blockchain initialized');
    console.log(`   Wallet: ${wallet.address}`);
    console.log(`   NENO Contract: ${NENO_CONTRACT_ADDRESS}`);
    console.log(`   BSC RPC: ${BSC_RPC_URLS.length} provider(s) configured`);
    console.log(`   Confirmations required: ${BSC_CONFIRMATIONS}`);
    console.log(`   Min threshold: ${MIN_CONFIRMATIONS_THRESHOLD}`);
    console.log(`   Dry-run mode: ${DRY_RUN_MODE}`);
    
    return true;
  } catch (error) {
    console.error('Failed to initialize blockchain:', error);
    return false;
  }
}

// Initialize on module load
const isBlockchainReady = initializeBlockchain();

/**
 * Get current provider with fallback
 */
async function getProvider() {
  const provider = providers[currentProviderIndex];
  
  try {
    // Test provider connectivity
    await provider.getBlockNumber();
    return provider;
  } catch (error) {
    console.error(`Provider ${currentProviderIndex} failed, switching to fallback`);
    
    // Try next provider
    currentProviderIndex = (currentProviderIndex + 1) % providers.length;
    
    if (currentProviderIndex === 0) {
      // Tried all providers
      throw new Error('All RPC providers failed');
    }
    
    return getProvider();
  }
}

/**
 * Get optimal gas price with throttling
 */
async function getOptimalGasPrice() {
  try {
    const provider = await getProvider();
    const feeData = await provider.getFeeData();
    
    let gasPrice = feeData.gasPrice;
    
    // Apply multiplier
    gasPrice = (gasPrice * BigInt(Math.floor(GAS_PRICE_MULTIPLIER * 100))) / BigInt(100);
    
    // Cap at max
    const maxGasPrice = ethers.parseUnits(MAX_GAS_PRICE_GWEI.toString(), 'gwei');
    if (gasPrice > maxGasPrice) {
      console.warn(`Gas price ${ethers.formatUnits(gasPrice, 'gwei')} Gwei exceeds max ${MAX_GAS_PRICE_GWEI} Gwei, capping`);
      gasPrice = maxGasPrice;
    }
    
    return gasPrice;
  } catch (error) {
    console.error('Failed to get gas price:', error);
    // Return default if fails
    return ethers.parseUnits('5', 'gwei');
  }
}

/**
 * Get next nonce with synchronization
 */
async function getNextNonce() {
  try {
    const provider = await getProvider();
    const currentNonce = await provider.getTransactionCount(wallet.address, 'pending');
    
    // Use cached nonce if higher
    if (nonceCache !== null && nonceCache >= currentNonce) {
      nonceCache++;
      console.log(`Using cached nonce: ${nonceCache}`);
      return nonceCache;
    }
    
    nonceCache = currentNonce;
    return currentNonce;
  } catch (error) {
    console.error('Failed to get nonce:', error);
    throw error;
  }
}

/**
 * Check if blockchain is configured and ready
 */
export function isBlockchainConfigured() {
  return isBlockchainReady && wallet && nenoContract;
}

/**
 * Get platform wallet balance
 */
export async function getWalletBalance() {
  if (!isBlockchainConfigured()) {
    throw new Error('Blockchain not configured');
  }

  try {
    const balance = await nenoContract.balanceOf(wallet.address);
    const decimals = await nenoContract.decimals();
    return ethers.formatUnits(balance, decimals);
  } catch (error) {
    console.error('Failed to get wallet balance:', error);
    throw error;
  }
}

/**
 * Send NENO tokens to user wallet (ONRAMP)
 */
export async function sendTokens(toAddress, amount, rampSessionId) {
  if (!isBlockchainConfigured()) {
    throw new Error('Blockchain not configured');
  }

  try {
    console.log(`Sending ${amount} NENO to ${toAddress} for session ${rampSessionId}`);

    // Convert amount to token units (18 decimals)
    const decimals = await nenoContract.decimals();
    const tokenAmount = ethers.parseUnits(amount.toString(), decimals);

    // Update status to pending
    await prisma.rampSession.update({
      where: { id: rampSessionId },
      data: {
        status: 'CHAIN_PENDING',
        txStatus: 'pending',
        lastProcessedAt: new Date(),
      },
    });

    // Send transaction
    const tx = await nenoContract.transfer(toAddress, tokenAmount);
    
    console.log(`Transaction sent: ${tx.hash}`);

    // Update with tx hash
    await prisma.rampSession.update({
      where: { id: rampSessionId },
      data: {
        txHash: tx.hash,
      },
    });

    // Wait for confirmation
    const receipt = await tx.wait(BSC_CONFIRMATIONS);

    console.log(`Transaction confirmed in block ${receipt.blockNumber}`);

    // Update as confirmed
    await prisma.rampSession.update({
      where: { id: rampSessionId },
      data: {
        status: 'CHAIN_CONFIRMED',
        txStatus: 'confirmed',
        blockNumber: receipt.blockNumber,
        gasUsed: receipt.gasUsed.toString(),
        lastProcessedAt: new Date(),
      },
    });

    return {
      success: true,
      txHash: tx.hash,
      blockNumber: receipt.blockNumber,
    };
  } catch (error) {
    console.error('Token transfer failed:', error);

    // Update as failed
    await prisma.rampSession.update({
      where: { id: rampSessionId },
      data: {
        status: 'FAILED',
        txStatus: 'failed',
        errorMessage: error.message,
        lastProcessedAt: new Date(),
      },
    });

    throw error;
  }
}

/**
 * Verify token receipt (OFFRAMP)
 * Check if tokens were received from user wallet
 */
export async function verifyTokenReceipt(fromAddress, amount, rampSessionId) {
  if (!isBlockchainConfigured()) {
    throw new Error('Blockchain not configured');
  }

  try {
    console.log(`Verifying receipt of ${amount} NENO from ${fromAddress} for session ${rampSessionId}`);

    // In production, this would:
    // 1. Monitor the blockchain for Transfer events
    // 2. Verify the exact amount was received
    // 3. Confirm the transaction
    
    // For MVP, we'll simulate verification
    // In production, implement proper event listening or transaction monitoring
    
    await prisma.rampSession.update({
      where: { id: rampSessionId },
      data: {
        status: 'CHAIN_PENDING',
        txStatus: 'verifying',
        lastProcessedAt: new Date(),
      },
    });

    // Simulate verification delay
    // In production, replace with actual blockchain verification
    
    return {
      verified: true,
      message: 'Token receipt verification pending - implement blockchain monitoring',
    };
  } catch (error) {
    console.error('Token verification failed:', error);
    throw error;
  }
}

/**
 * Get transaction status from blockchain
 */
export async function getTransactionStatus(txHash) {
  if (!isBlockchainConfigured()) {
    throw new Error('Blockchain not configured');
  }

  try {
    const receipt = await provider.getTransactionReceipt(txHash);
    
    if (!receipt) {
      return { status: 'pending', confirmed: false };
    }

    const currentBlock = await provider.getBlockNumber();
    const confirmations = currentBlock - receipt.blockNumber;

    return {
      status: receipt.status === 1 ? 'success' : 'failed',
      confirmed: confirmations >= BSC_CONFIRMATIONS,
      confirmations,
      blockNumber: receipt.blockNumber,
    };
  } catch (error) {
    console.error('Failed to get transaction status:', error);
    throw error;
  }
}

/**
 * Complete onramp flow: send tokens after payment confirmation
 */
export async function processOnramp(rampSessionId) {
  const session = await prisma.rampSession.findUnique({
    where: { id: rampSessionId },
  });

  if (!session) {
    throw new Error('Session not found');
  }

  if (session.type !== 'ONRAMP') {
    throw new Error('Not an onramp session');
  }

  if (session.status !== 'PAYMENT_CONFIRMED') {
    throw new Error(`Invalid status for onramp: ${session.status}`);
  }

  if (!session.userWallet) {
    throw new Error('User wallet not specified');
  }

  try {
    const result = await sendTokens(
      session.userWallet,
      parseFloat(session.tokens),
      rampSessionId
    );

    // Mark as completed
    await prisma.rampSession.update({
      where: { id: rampSessionId },
      data: {
        status: 'COMPLETED',
      },
    });

    return result;
  } catch (error) {
    console.error('Onramp processing failed:', error);
    throw error;
  }
}

/**
 * Complete offramp flow: verify tokens received, then process payout
 */
export async function processOfframp(rampSessionId) {
  const session = await prisma.rampSession.findUnique({
    where: { id: rampSessionId },
  });

  if (!session) {
    throw new Error('Session not found');
  }

  if (session.type !== 'OFFRAMP') {
    throw new Error('Not an offramp session');
  }

  if (session.status !== 'PAYMENT_CONFIRMED') {
    throw new Error(`Invalid status for offramp: ${session.status}`);
  }

  try {
    // Verify tokens were received
    const verification = await verifyTokenReceipt(
      session.userWallet,
      parseFloat(session.tokens),
      rampSessionId
    );

    if (verification.verified) {
      // In production, trigger fiat payout here
      // For now, mark as completed
      await prisma.rampSession.update({
        where: { id: rampSessionId },
        data: {
          status: 'COMPLETED',
          txStatus: 'confirmed',
        },
      });
    }

    return verification;
  } catch (error) {
    console.error('Offramp processing failed:', error);
    throw error;
  }
}
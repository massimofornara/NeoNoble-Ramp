const fs = require('node:fs');
const path = require('node:path');
const { PrismaClient } = require('@prisma/client');
const { ethers } = require('ethers');

const ERC20_ABI = [
  'event Transfer(address indexed from, address indexed to, uint256 value)',
];

function loadEnvFile() {
  const envPath = path.join(process.cwd(), '.env');
  if (!fs.existsSync(envPath)) return;

  for (const line of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
    const index = trimmed.indexOf('=');
    const key = trimmed.slice(0, index).trim();
    const rawValue = trimmed.slice(index + 1).trim();
    if (!process.env[key]) {
      process.env[key] = rawValue.replace(/^"(.*)"$/, '$1');
    }
  }
}

function getProvider() {
  const rpcUrl = String(process.env.BSC_RPC_URL || process.env.BSC_RPC_URLS || 'https://bsc-dataseed1.binance.org/')
    .split(',')
    .map((url) => url.trim())
    .find(Boolean);

  if (!rpcUrl) {
    throw new Error('BSC_RPC_URL is required');
  }

  return new ethers.JsonRpcProvider(rpcUrl, Number(process.env.BSC_CHAIN_ID || 56));
}

function getAllowedFromAddresses() {
  const addresses = new Set();

  for (const key of ['HOT_WALLET_ADDRESS', 'EXCHANGE_HOT_WALLET_ADDRESS']) {
    if (process.env[key] && ethers.isAddress(process.env[key])) {
      addresses.add(ethers.getAddress(process.env[key]).toLowerCase());
    }
  }

  const privateKey = process.env.HOT_WALLET_PRIVATE_KEY || process.env.BSC_PRIVATE_KEY;
  if (privateKey) {
    try {
      addresses.add(new ethers.Wallet(privateKey).address.toLowerCase());
    } catch {
      // Do not emit secret-derived details.
    }
  }

  for (const raw of String(process.env.USER_WALLET_ALLOWLIST || '').split(',')) {
    const address = raw.trim();
    if (address && ethers.isAddress(address)) {
      addresses.add(ethers.getAddress(address).toLowerCase());
    }
  }

  return addresses;
}

function isValidTxHash(txHash) {
  return typeof txHash === 'string' && /^0x[0-9a-fA-F]{64}$/.test(txHash);
}

async function emitEvent(prisma, transactionId, eventType, payload = {}) {
  const event = await prisma.transactionEvent.create({
    data: {
      transactionId,
      eventType,
      payload,
    },
  });
  return event;
}

function parseTransfer(receipt) {
  const iface = new ethers.Interface(ERC20_ABI);
  for (const log of receipt.logs || []) {
    try {
      const parsed = iface.parseLog(log);
      if (parsed && parsed.name === 'Transfer') {
        return {
          tokenAddress: log.address,
          tokenFrom: parsed.args.from,
          tokenTo: parsed.args.to,
          tokenValue: parsed.args.value.toString(),
        };
      }
    } catch {
      // Ignore non-ERC20 logs.
    }
  }
  return null;
}

function statusFromReceipt(receipt, confirmations, finalityThreshold) {
  if (!receipt || receipt.status !== 1) {
    return {
      status: 'failed_chain_validation',
      chainStatus: 'failed',
      step: 'chain_failed_validation',
      finalState: 'failed_chain_validation',
    };
  }

  if (confirmations >= finalityThreshold) {
    return {
      status: 'settled',
      chainStatus: 'finalized',
      step: 'finalized',
      finalState: 'settled',
    };
  }

  return {
    status: 'confirmed',
    chainStatus: 'confirmed',
    step: 'chain_confirmed',
    finalState: 'confirmed',
  };
}

function addAmount(map, asset, amount) {
  if (!asset) return;
  const key = String(asset).toUpperCase();
  map.set(key, (map.get(key) || 0n) + amount);
}

const SCALE = 18n;
const BASE = 10n ** SCALE;

function decimalToScaled(value) {
  if (value === undefined || value === null || value === '') return 0n;
  const raw = String(value);
  const negative = raw.startsWith('-');
  const unsigned = negative ? raw.slice(1) : raw;
  const [whole, fraction = ''] = unsigned.split('.');
  const scaled = BigInt(whole || '0') * BASE + BigInt((fraction + '0'.repeat(Number(SCALE))).slice(0, Number(SCALE)));
  return negative ? -scaled : scaled;
}

function scaledToDecimal(value) {
  const negative = value < 0n;
  const unsigned = negative ? -value : value;
  const whole = unsigned / BASE;
  const fraction = (unsigned % BASE).toString().padStart(Number(SCALE), '0').replace(/0+$/, '');
  return `${negative ? '-' : ''}${whole.toString()}${fraction ? `.${fraction}` : ''}`;
}

function deriveBalances(transactions) {
  const balances = new Map();

  for (const transaction of transactions) {
    const status = String(transaction.status).toLowerCase();
    const chainStatus = String(transaction.chainStatus || '').toLowerCase();
    const hasChainProof = Boolean(transaction.txHash) && transaction.blockNumber !== null && ['confirmed', 'finalized'].includes(chainStatus);

    if (!(status === 'confirmed' || status === 'settled') || !hasChainProof) continue;

    const type = String(transaction.type).toLowerCase();
    const fromToken = transaction.fromToken && String(transaction.fromToken).toUpperCase();
    const toToken = transaction.toToken && String(transaction.toToken).toUpperCase();
    const fiatCurrency = transaction.fiatCurrency && String(transaction.fiatCurrency).toUpperCase();
    const cryptoAmount = decimalToScaled(transaction.cryptoAmount);
    const fiatAmount = decimalToScaled(transaction.fiatAmount);

    if (type === 'onramp') {
      addAmount(balances, toToken, cryptoAmount);
    } else if (type === 'offramp') {
      addAmount(balances, fromToken, -cryptoAmount);
      addAmount(balances, fiatCurrency || toToken, fiatAmount);
    } else if (type === 'swap') {
      addAmount(balances, fromToken, -cryptoAmount);
      addAmount(balances, toToken, fiatAmount || cryptoAmount);
    }
  }

  return Object.fromEntries(Array.from(balances.entries()).map(([asset, amount]) => [asset, scaledToDecimal(amount)]));
}

async function markFailed(prisma, transaction, reason, extra = {}) {
  await prisma.transaction.update({
    where: { id: transaction.id },
    data: {
      status: 'failed_chain_validation',
      chainStatus: 'invalid_chain_tx',
      step: 'chain_failed_validation',
      confirmations: 0,
      errorMessage: reason,
      rawTxData: {
        ...(transaction.rawTxData || {}),
        chainValidation: {
          reason,
          ...extra,
        },
      },
    },
  });
  await emitEvent(prisma, transaction.id, 'chain.failed_validation', { reason, ...extra });
}

async function validateTransaction(prisma, provider, allowedFromAddresses, transaction, currentBlock, finalityThreshold) {
  const oldStatus = transaction.status;
  await emitEvent(prisma, transaction.id, 'chain.sync.started', {
    oldStatus,
    txHash: transaction.txHash,
  });

  if (!isValidTxHash(transaction.txHash)) {
    await markFailed(prisma, transaction, 'missing_or_invalid_tx_hash');
    return {
      transactionId: transaction.id,
      oldStatus,
      newStatus: 'failed_chain_validation',
      chainVerified: false,
      blockNumber: null,
      confirmations: 0,
      finalState: 'failed_chain_validation',
      anomaly: 'missing_or_invalid_tx_hash',
    };
  }

  const [chainTx, receipt] = await Promise.all([
    provider.getTransaction(transaction.txHash),
    provider.getTransactionReceipt(transaction.txHash),
  ]);

  if (!chainTx || !receipt) {
    await markFailed(prisma, transaction, chainTx ? 'missing_receipt' : 'tx_not_found_on_bsc');
    return {
      transactionId: transaction.id,
      oldStatus,
      newStatus: 'failed_chain_validation',
      chainVerified: false,
      blockNumber: receipt ? receipt.blockNumber : null,
      confirmations: 0,
      finalState: 'failed_chain_validation',
      anomaly: chainTx ? 'missing_receipt' : 'tx_not_found_on_bsc',
    };
  }

  const fromAddress = ethers.getAddress(chainTx.from);
  if (allowedFromAddresses.size === 0 || !allowedFromAddresses.has(fromAddress.toLowerCase())) {
    await markFailed(prisma, transaction, 'unauthorized_from_address', {
      fromAddress,
      allowedWalletConfigured: allowedFromAddresses.size > 0,
    });
    return {
      transactionId: transaction.id,
      oldStatus,
      newStatus: 'failed_chain_validation',
      chainVerified: false,
      blockNumber: receipt.blockNumber,
      confirmations: Math.max(currentBlock - receipt.blockNumber + 1, 0),
      finalState: 'failed_chain_validation',
      anomaly: 'unauthorized_from_address',
    };
  }

  const confirmations = Math.max(currentBlock - receipt.blockNumber + 1, 0);
  const transfer = parseTransfer(receipt);
  const next = statusFromReceipt(receipt, confirmations, finalityThreshold);

  if (receipt.status !== 1) {
    await markFailed(prisma, transaction, 'receipt_status_failed', {
      blockNumber: receipt.blockNumber,
      confirmations,
    });
  } else {
    await prisma.transaction.update({
      where: { id: transaction.id },
      data: {
        status: next.status,
        chainStatus: next.chainStatus,
        step: next.step,
        blockNumber: receipt.blockNumber,
        gasUsed: receipt.gasUsed.toString(),
        confirmations,
        fromAddress,
        toAddress: transfer ? ethers.getAddress(transfer.tokenTo) : chainTx.to ? ethers.getAddress(chainTx.to) : null,
        rawTxData: {
          hash: chainTx.hash,
          nonce: chainTx.nonce,
          from: fromAddress,
          to: chainTx.to,
          value: chainTx.value.toString(),
          data: chainTx.data,
          tokenTransfer: transfer,
          receiptStatus: receipt.status,
          validatedAt: new Date().toISOString(),
        },
        errorMessage: null,
      },
    });

    await emitEvent(prisma, transaction.id, 'chain.tx.validated', {
      txHash: chainTx.hash,
      blockNumber: receipt.blockNumber,
      gasUsed: receipt.gasUsed.toString(),
      confirmations,
      fromAddress,
      toAddress: transfer ? transfer.tokenTo : chainTx.to,
    });

    await emitEvent(prisma, transaction.id, 'chain.confirmed', {
      confirmations,
      blockNumber: receipt.blockNumber,
    });

    if (next.status === 'settled') {
      await emitEvent(prisma, transaction.id, 'chain.settled', {
        confirmations,
        blockNumber: receipt.blockNumber,
      });
    }
  }

  return {
    transactionId: transaction.id,
    oldStatus,
    newStatus: next.status,
    chainVerified: receipt.status === 1,
    blockNumber: receipt.blockNumber,
    confirmations,
    finalState: next.finalState,
  };
}

async function main() {
  loadEnvFile();
  if (!process.env.DATABASE_URL || process.env.DATABASE_URL.includes('@postgres:')) {
    process.env.DATABASE_URL = 'postgresql://neonoble:neonoble123@localhost:5432/neonoble_ramp';
  }

  const prisma = new PrismaClient();
  const provider = getProvider();
  const allowedFromAddresses = getAllowedFromAddresses();
  const finalityThreshold = Number.parseInt(process.env.BSC_FINALITY_CONFIRMATIONS || '12', 10);
  const currentBlock = await provider.getBlockNumber();

  try {
    const transactions = await prisma.transaction.findMany({
      orderBy: { createdAt: 'asc' },
    });

    const report = [];
    for (const transaction of transactions) {
      report.push(await validateTransaction(prisma, provider, allowedFromAddresses, transaction, currentBlock, finalityThreshold));
    }

    const refreshed = await prisma.transaction.findMany({ orderBy: { createdAt: 'asc' } });
    const users = Array.from(new Set(refreshed.map((transaction) => transaction.userId)));
    const ledger = {};
    for (const userId of users) {
      ledger[userId] = deriveBalances(refreshed.filter((transaction) => transaction.userId === userId));
    }

    const anomalies = report
      .filter((item) => !item.chainVerified)
      .map((item) => ({
        transactionId: item.transactionId,
        anomaly: item.anomaly || item.finalState,
        oldStatus: item.oldStatus,
        newStatus: item.newStatus,
      }));

    const auditLog = await prisma.transactionEvent.findMany({
      where: {
        eventType: {
          in: ['chain.sync.started', 'chain.tx.validated', 'chain.confirmed', 'chain.settled', 'chain.failed_validation'],
        },
      },
      orderBy: { createdAt: 'desc' },
      take: Math.max(report.length * 5, 50),
    });

    console.log(
      JSON.stringify(
        {
          migratedAt: new Date().toISOString(),
          currentBlock,
          finalityThreshold,
          allowedWalletConfigured: allowedFromAddresses.size > 0,
          report,
          ledger,
          anomalies,
          auditLog: auditLog.map((event) => ({
            id: event.id,
            transactionId: event.transactionId,
            eventType: event.eventType,
            payload: event.payload,
            createdAt: event.createdAt,
          })),
        },
        null,
        2,
      ),
    );
  } finally {
    await prisma.$disconnect();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

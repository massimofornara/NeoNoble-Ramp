/**
 * NeoNoble real execution worker.
 *
 * Lifecycle:
 * routing_active -> execution_attempted -> settlement_pending -> settlement_confirmed
 *
 * This worker never fabricates tx hashes and never completes transactions by
 * elapsed time. Finality comes from BSC receipts or PSP webhook settlement.
 */

const { PrismaClient } = require('@prisma/client');
const { executeOnChainPayout, executeSwapOnChain } = require('../lib/blockchain/blockchainService.cjs');
const { updateBroadcastedTransaction } = require('../lib/blockchain/confirmationListener.cjs');
const { getHotWalletAddressForChain } = require('../lib/blockchain/walletService.cjs');
const { publishTransactionEvent } = require('../lib/events/eventBus.cjs');

const prisma = new PrismaClient();

const WORKER_INTERVAL_MS = Number.parseInt(process.env.WORKER_INTERVAL_MS || '5000', 10);
const WORKER_ENABLED = process.env.WORKER_ENABLED !== 'false';
const LEDGER_BATCH_SIZE = Number.parseInt(process.env.LEDGER_WORKER_BATCH_SIZE || '10', 10);
const DEFERRED_SETTLEMENT_RETRY_MS = Number.parseInt(process.env.DEFERRED_SETTLEMENT_RETRY_MS || '60000', 10);

let isRunning = false;
let loopCount = 0;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function claimPendingTransaction(transaction) {
  const fromAddress = await getHotWalletAddressForChain(transaction.chainName || transaction.network || 'BSC');
  const claimed = await prisma.transaction.updateMany({
    where: {
      id: transaction.id,
      status: { in: ['routing_active', 'pending'] },
    },
    data: {
      status: 'execution_attempted',
      step: 'tx_signed',
      fromAddress,
      chainStatus: 'signed',
      finalityStatus: 'routing_active',
      lastSuccessfulRail: 'onchain',
    },
  });

  if (claimed.count === 1) {
    await publishTransactionEvent(transaction.id, 'transaction.signed', {
      fromAddress,
      type: transaction.type,
    });
  }

  return claimed.count === 1;
}

async function broadcastTransaction(transaction) {
  const fresh = await prisma.transaction.findUnique({ where: { id: transaction.id } });
  if (!fresh || !['pending', 'broadcasting', 'routing_active', 'execution_attempted'].includes(fresh.status)) return;

  let broadcast;
  if (fresh.type === 'swap') {
    broadcast = await executeSwapOnChain(fresh);
  } else if (fresh.type === 'offramp') {
    broadcast = await executeOnChainPayout(fresh);
  } else {
    throw new Error(`Transaction type ${fresh.type} is not executable by blockchain worker`);
  }

  await prisma.transaction.update({
    where: { id: fresh.id },
    data: {
      status: 'execution_successful',
      step: 'execution_successful',
      chainStatus: 'pending',
      finalityStatus: 'settlement_pending',
      txHash: broadcast.txHash,
      fromAddress: broadcast.fromAddress,
      toAddress: broadcast.toAddress,
      chainId: broadcast.rawTxData.chainId,
      chainName: broadcast.rawTxData.chainName,
      settlementLayer: broadcast.rawTxData.settlementLayer,
      rawTxData: broadcast.rawTxData,
      lastSuccessfulRail: 'onchain',
    },
  });

  await publishTransactionEvent(fresh.id, 'execution.successful', {
    txHash: broadcast.txHash,
    fromAddress: broadcast.fromAddress,
    toAddress: broadcast.toAddress,
    settlementLayer: broadcast.rawTxData.settlementLayer,
  });

  await publishTransactionEvent(fresh.id, 'transaction.broadcasted', {
    txHash: broadcast.txHash,
    fromAddress: broadcast.fromAddress,
    toAddress: broadcast.toAddress,
  });
}

async function failTransaction(transaction, error, step = 'execution_failed') {
  await prisma.transaction.update({
    where: { id: transaction.id },
    data: {
      status: 'failed_unrecoverable',
      step,
      chainStatus: transaction.chainStatus || 'failed',
      finalityStatus: 'failed_unrecoverable',
      errorMessage: error.message,
    },
  });

  await publishTransactionEvent(transaction.id, 'transaction.failed', {
    error: error.message,
    step,
  });
}

async function processPendingTransactions() {
  const transactions = await prisma.transaction.findMany({
    where: {
      status: { in: ['routing_active', 'pending'] },
      type: { in: ['swap', 'offramp'] },
      step: { in: ['onchain_execution_queued', 'init'] },
    },
    orderBy: { createdAt: 'asc' },
    take: LEDGER_BATCH_SIZE,
  });

  for (const transaction of transactions) {
    try {
      const claimed = await claimPendingTransaction(transaction);
      if (claimed) {
        await broadcastTransaction(transaction);
      }
    } catch (error) {
      await failTransaction(transaction, error);
    }
  }
}

async function processSignedTransactions() {
  const transactions = await prisma.transaction.findMany({
    where: {
      status: 'execution_attempted',
      type: { in: ['swap', 'offramp'] },
      step: { in: ['tx_signed', 'onchain_execution_queued'] },
    },
    orderBy: { updatedAt: 'asc' },
    take: LEDGER_BATCH_SIZE,
  });

  for (const transaction of transactions) {
    try {
      await broadcastTransaction(transaction);
    } catch (error) {
      await failTransaction(transaction, error);
    }
  }
}

async function monitorBroadcastedTransactions() {
  const transactions = await prisma.transaction.findMany({
    where: {
      status: { in: ['settlement_pending', 'execution_successful', 'execution_attempted', 'confirmed'] },
      txHash: { not: null },
    },
    orderBy: { updatedAt: 'asc' },
    take: LEDGER_BATCH_SIZE,
  });

  for (const transaction of transactions) {
    try {
      await updateBroadcastedTransaction(prisma, transaction);
    } catch (error) {
      await failTransaction(transaction, error, 'confirmation_failed');
    }
  }
}

async function retryDeferredSettlementTransactions() {
  const retryBefore = new Date(Date.now() - DEFERRED_SETTLEMENT_RETRY_MS);
  const transactions = await prisma.transaction.findMany({
    where: {
      status: { in: ['settlement_pending', 'execution_fallback_active', 'execution_attempted'] },
      step: {
        in: [
          'deferred_settlement_active',
          'provider_failed_retrying',
          'awaiting_real_liquidity',
          'liquidity_bootstrap_active',
          'settlement_source_ready',
        ],
      },
      txHash: null,
      updatedAt: { lte: retryBefore },
    },
    orderBy: { updatedAt: 'asc' },
    take: LEDGER_BATCH_SIZE,
  });

  if (transactions.length === 0) return;

  const { routeExecution } = await import('../lib/execution/executionRouter.js');
  for (const transaction of transactions) {
    try {
      await publishTransactionEvent(transaction.id, 'execution.closure_loop_retry_started', {
        retryAfterMs: DEFERRED_SETTLEMENT_RETRY_MS,
        previousStep: transaction.step,
      });
      await routeExecution(transaction, { origin: process.env.NEXT_PUBLIC_APP_URL || process.env.APP_URL });
    } catch (error) {
      await prisma.transaction.update({
        where: { id: transaction.id },
        data: {
          status: 'execution_attempted',
          step: 'awaiting_real_liquidity',
          finalityStatus: 'execution_attempted',
          chainStatus: 'funding_required',
          errorMessage: error.message,
        },
      });
      await publishTransactionEvent(transaction.id, 'execution.closure_loop_retry_failed', {
        error: error.message,
      });
    }
  }
}

async function getWorkerStats() {
  const statuses = await prisma.transaction.groupBy({
    by: ['status'],
    _count: { status: true },
  });

  return Object.fromEntries(statuses.map((row) => [row.status, row._count.status]));
}

async function processTransactions() {
  await processPendingTransactions();
  await processSignedTransactions();
  await monitorBroadcastedTransactions();
  await retryDeferredSettlementTransactions();

  if (loopCount % 12 === 0) {
    console.log(JSON.stringify({ event: 'worker.stats', stats: await getWorkerStats() }));
  }

  loopCount += 1;
}

async function workerLoop() {
  if (!WORKER_ENABLED) {
    console.log(JSON.stringify({ event: 'worker.disabled' }));
    return;
  }

  console.log(
    JSON.stringify({
      event: 'worker.started',
      mode: process.env.BLOCKCHAIN_EXECUTION_MODE || 'disabled',
      intervalMs: WORKER_INTERVAL_MS,
      batchSize: LEDGER_BATCH_SIZE,
    }),
  );

  while (isRunning) {
    try {
      await processTransactions();
    } catch (error) {
      console.error(JSON.stringify({ event: 'worker.loop_error', error: error.message }));
    }

    await sleep(WORKER_INTERVAL_MS);
  }
}

async function shutdown() {
  console.log(JSON.stringify({ event: 'worker.shutdown' }));
  isRunning = false;
  await sleep(1000);
  await prisma.$disconnect();
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

isRunning = true;
workerLoop().catch(async (error) => {
  console.error(JSON.stringify({ event: 'worker.fatal', error: error.message }));
  await prisma.$disconnect();
  process.exit(1);
});

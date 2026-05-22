/**
 * Background Worker for Processing Ramp Transactions
 * 
 * This worker continuously monitors and processes ramp sessions:
 * - PAYMENT_CONFIRMED → Process onramp/offramp
 * - CHAIN_PENDING → Monitor blockchain confirmations
 * - Retry failed transactions
 * 
 * Run with: node workers/transactionWorker.js
 */

const { PrismaClient } = require('@prisma/client');
const { processOnramp, processOfframp, getTransactionStatus } = require('../lib/services/blockchainService');

const prisma = new PrismaClient();

const WORKER_INTERVAL_MS = parseInt(process.env.WORKER_INTERVAL_MS || '5000', 10);
const WORKER_ENABLED = process.env.WORKER_ENABLED !== 'false';
const MAX_RETRY_COUNT = 3;

let isRunning = false;
let processingCount = 0;

/**
 * Main worker loop
 */
async function workerLoop() {
  if (!WORKER_ENABLED) {
    console.log('⚠️  Worker is disabled (WORKER_ENABLED=false)');
    return;
  }

  console.log('🚀 Transaction Worker started');
  console.log(`   Interval: ${WORKER_INTERVAL_MS}ms`);
  console.log(`   Max retries: ${MAX_RETRY_COUNT}`);

  while (isRunning) {
    try {
      await processTransactions();
    } catch (error) {
      console.error('Worker loop error:', error);
    }

    // Wait before next iteration
    await sleep(WORKER_INTERVAL_MS);
  }
}

/**
 * Process pending transactions
 */
async function processTransactions() {
  try {
    // Process payment-confirmed sessions (send tokens)
    await processPaymentConfirmedSessions();

    // Monitor chain-pending transactions
    await monitorChainPendingTransactions();

    // Retry failed transactions
    await retryFailedTransactions();

    if (processingCount % 12 === 0) {
      // Log status every minute (12 * 5 seconds)
      const stats = await getWorkerStats();
      console.log(`📊 Worker stats: ${JSON.stringify(stats)}`);
    }

    processingCount++;
  } catch (error) {
    console.error('Error processing transactions:', error);
  }
}

/**
 * Process sessions that have payment confirmed
 */
async function processPaymentConfirmedSessions() {
  const sessions = await prisma.rampSession.findMany({
    where: {
      status: 'PAYMENT_CONFIRMED',
      retryCount: {
        lt: MAX_RETRY_COUNT,
      },
    },
    orderBy: {
      createdAt: 'asc',
    },
    take: 10, // Process in batches
  });

  for (const session of sessions) {
    try {
      console.log(`Processing ${session.type} session: ${session.id}`);

      if (session.type === 'ONRAMP') {
        await processOnramp(session.id);
        console.log(`✅ Onramp completed: ${session.id}`);
      } else if (session.type === 'OFFRAMP') {
        await processOfframp(session.id);
        console.log(`✅ Offramp completed: ${session.id}`);
      }
    } catch (error) {
      console.error(`Failed to process session ${session.id}:`, error);
      
      // Increment retry count
      await prisma.rampSession.update({
        where: { id: session.id },
        data: {
          retryCount: { increment: 1 },
          errorMessage: error.message,
          lastProcessedAt: new Date(),
        },
      });

      // If max retries reached, mark as failed
      if (session.retryCount + 1 >= MAX_RETRY_COUNT) {
        await prisma.rampSession.update({
          where: { id: session.id },
          data: {
            status: 'FAILED',
          },
        });
        console.error(`❌ Session ${session.id} failed after ${MAX_RETRY_COUNT} retries`);
      }
    }
  }
}

/**
 * Monitor chain-pending transactions
 */
async function monitorChainPendingTransactions() {
  const sessions = await prisma.rampSession.findMany({
    where: {
      status: 'CHAIN_PENDING',
      txHash: {
        not: null,
      },
    },
    orderBy: {
      createdAt: 'asc',
    },
    take: 20,
  });

  for (const session of sessions) {
    try {
      const txStatus = await getTransactionStatus(session.txHash);

      if (txStatus.confirmed) {
        // Transaction confirmed
        await prisma.rampSession.update({
          where: { id: session.id },
          data: {
            status: 'CHAIN_CONFIRMED',
            txStatus: 'confirmed',
            blockNumber: txStatus.blockNumber,
          },
        });

        // Mark as completed
        await prisma.rampSession.update({
          where: { id: session.id },
          data: {
            status: 'COMPLETED',
          },
        });

        console.log(`✅ Transaction confirmed: ${session.id} (tx: ${session.txHash})`);
      } else if (txStatus.status === 'failed') {
        // Transaction failed
        await prisma.rampSession.update({
          where: { id: session.id },
          data: {
            status: 'FAILED',
            txStatus: 'failed',
            errorMessage: 'Blockchain transaction failed',
          },
        });

        console.error(`❌ Transaction failed: ${session.id} (tx: ${session.txHash})`);
      } else {
        console.log(`⏳ Transaction pending: ${session.id} (confirmations: ${txStatus.confirmations || 0})`);
      }
    } catch (error) {
      console.error(`Error monitoring transaction ${session.id}:`, error);
    }
  }
}

/**
 * Retry failed transactions that can be retried
 */
async function retryFailedTransactions() {
  const sessions = await prisma.rampSession.findMany({
    where: {
      status: 'FAILED',
      retryCount: {
        lt: MAX_RETRY_COUNT,
      },
      lastProcessedAt: {
        lt: new Date(Date.now() - 5 * 60 * 1000), // Last attempt > 5 minutes ago
      },
    },
    orderBy: {
      createdAt: 'asc',
    },
    take: 5,
  });

  for (const session of sessions) {
    console.log(`Retrying failed session: ${session.id} (attempt ${session.retryCount + 1}/${MAX_RETRY_COUNT})`);
    
    // Reset status to allow reprocessing
    await prisma.rampSession.update({
      where: { id: session.id },
      data: {
        status: 'PAYMENT_CONFIRMED',
        errorMessage: null,
      },
    });
  }
}

/**
 * Get worker statistics
 */
async function getWorkerStats() {
  const [
    pending,
    awaitingPayment,
    processing,
    paymentConfirmed,
    chainPending,
    chainConfirmed,
    completed,
    failed,
  ] = await Promise.all([
    prisma.rampSession.count({ where: { status: 'PENDING' } }),
    prisma.rampSession.count({ where: { status: 'AWAITING_PAYMENT' } }),
    prisma.rampSession.count({ where: { status: 'PROCESSING' } }),
    prisma.rampSession.count({ where: { status: 'PAYMENT_CONFIRMED' } }),
    prisma.rampSession.count({ where: { status: 'CHAIN_PENDING' } }),
    prisma.rampSession.count({ where: { status: 'CHAIN_CONFIRMED' } }),
    prisma.rampSession.count({ where: { status: 'COMPLETED' } }),
    prisma.rampSession.count({ where: { status: 'FAILED' } }),
  ]);

  return {
    pending,
    awaitingPayment,
    processing,
    paymentConfirmed,
    chainPending,
    chainConfirmed,
    completed,
    failed,
    total: pending + awaitingPayment + processing + paymentConfirmed + chainPending + chainConfirmed + completed + failed,
  };
}

/**
 * Sleep utility
 */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Graceful shutdown
 */
async function shutdown() {
  console.log('\n🛑 Shutting down worker...');
  isRunning = false;
  
  // Wait a bit for current processing to finish
  await sleep(2000);
  
  await prisma.$disconnect();
  console.log('✅ Worker stopped');
  process.exit(0);
}

// Handle shutdown signals
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// Start worker
isRunning = true;
workerLoop().catch((error) => {
  console.error('Fatal worker error:', error);
  process.exit(1);
});

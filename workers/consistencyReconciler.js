/**
 * Consistency Reconciler for NeoNoble Ramp
 * 
 * Periodically scans for stuck or inconsistent sessions and repairs them
 * Ensures no session remains in unknown or invalid state
 * 
 * Run: node workers/consistencyReconciler.js
 */

const { PrismaClient } = require('@prisma/client');
const { getPaymentProvider } = require('../lib/services/paymentService');
const { getTransactionStatus, isBlockchainConfigured } = require('../lib/services/blockchainService');

const prisma = new PrismaClient();

const RECONCILE_INTERVAL_MS = parseInt(process.env.RECONCILE_INTERVAL_MS || '60000', 10); // 1 minute
const STUCK_SESSION_THRESHOLD_MS = 30 * 60 * 1000; // 30 minutes
const MAX_SESSION_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

let isRunning = false;
let reconciliationCount = 0;

class ConsistencyReconciler {
  /**
   * Main reconciliation loop
   */
  static async run() {
    if (!isRunning) return;

    try {
      console.log(`🔍 [Reconciler] Starting reconciliation cycle #${reconciliationCount + 1}`);
      
      const results = {
        stuckSessions: 0,
        paymentMismatches: 0,
        blockchainRechecks: 0,
        stateRepairs: 0,
        expired: 0,
      };

      // 1. Check stuck sessions
      results.stuckSessions = await this.checkStuckSessions();

      // 2. Verify payment status mismatches
      results.paymentMismatches = await this.verifyPaymentStatus();

      // 3. Re-check blockchain confirmations
      results.blockchainRechecks = await this.recheckBlockchainConfirmations();

      // 4. Repair invalid states
      results.stateRepairs = await this.repairInvalidStates();

      // 5. Mark expired sessions
      results.expired = await this.markExpiredSessions();

      console.log(`✅ [Reconciler] Cycle complete:`, results);
      reconciliationCount++;

      // Log reconciliation stats
      await this.logReconciliationStats(results);
    } catch (error) {
      console.error('❌ [Reconciler] Error:', error);
      await this.logReconciliationError(error);
    }
  }

  /**
   * Check for stuck sessions that haven't progressed
   */
  static async checkStuckSessions() {
    const stuckThreshold = new Date(Date.now() - STUCK_SESSION_THRESHOLD_MS);
    
    const stuckSessions = await prisma.rampSession.findMany({
      where: {
        status: {
          in: ['AWAITING_PAYMENT', 'PROCESSING', 'PAYMENT_CONFIRMED', 'CHAIN_PENDING'],
        },
        updatedAt: {
          lt: stuckThreshold,
        },
        retryCount: {
          lt: 3,
        },
      },
    });

    console.log(`   Found ${stuckSessions.length} stuck sessions`);

    for (const session of stuckSessions) {
      try {
        console.log(`   🔧 Repairing stuck session: ${session.id} (status: ${session.status})`);
        
        if (session.status === 'AWAITING_PAYMENT' && session.paymentSessionId) {
          // Re-check payment status
          await this.recheckPayment(session);
        } else if (session.status === 'PAYMENT_CONFIRMED') {
          // Trigger worker to reprocess
          await prisma.rampSession.update({
            where: { id: session.id },
            data: {
              lastProcessedAt: new Date(),
              errorMessage: 'Stuck session - queued for reprocessing',
            },
          });
        } else if (session.status === 'CHAIN_PENDING' && session.txHash) {
          // Re-check blockchain status
          await this.recheckTransaction(session);
        }
      } catch (error) {
        console.error(`   ❌ Failed to repair session ${session.id}:`, error);
      }
    }

    return stuckSessions.length;
  }

  /**
   * Verify payment status matches between Stripe and our DB
   */
  static async verifyPaymentStatus() {
    const sessionsToVerify = await prisma.rampSession.findMany({
      where: {
        status: {
          in: ['AWAITING_PAYMENT', 'PROCESSING'],
        },
        paymentProvider: 'live',
        paymentSessionId: {
          not: null,
        },
      },
      take: 50,
    });

    console.log(`   Verifying ${sessionsToVerify.length} payment statuses`);

    let mismatches = 0;

    for (const session of sessionsToVerify) {
      try {
        const provider = getPaymentProvider();
        const paymentStatus = await provider.getSessionStatus(session.paymentSessionId);

        if (paymentStatus.status === 'paid' && session.status !== 'PAYMENT_CONFIRMED') {
          console.log(`   🔧 Payment mismatch detected: ${session.id} - Stripe says paid, DB says ${session.status}`);
          
          await prisma.rampSession.update({
            where: { id: session.id },
            data: {
              status: 'PAYMENT_CONFIRMED',
              paymentStatus: 'paid',
              paymentIntentId: paymentStatus.paymentIntentId,
              lastProcessedAt: new Date(),
            },
          });

          mismatches++;
        }
      } catch (error) {
        console.error(`   ❌ Failed to verify payment for ${session.id}:`, error);
      }
    }

    return mismatches;
  }

  /**
   * Re-check blockchain confirmations for pending transactions
   */
  static async recheckBlockchainConfirmations() {
    if (!isBlockchainConfigured()) {
      return 0;
    }

    const pendingTxs = await prisma.rampSession.findMany({
      where: {
        status: 'CHAIN_PENDING',
        txHash: {
          not: null,
        },
      },
      take: 100,
    });

    console.log(`   Re-checking ${pendingTxs.length} blockchain transactions`);

    let rechecked = 0;

    for (const session of pendingTxs) {
      try {
        const txStatus = await getTransactionStatus(session.txHash);

        if (txStatus.confirmed) {
          console.log(`   ✅ Transaction confirmed: ${session.id} (tx: ${session.txHash})`);
          
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
            data: { status: 'COMPLETED' },
          });

          rechecked++;
        } else if (txStatus.status === 'failed') {
          console.log(`   ❌ Transaction failed: ${session.id} (tx: ${session.txHash})`);
          
          await prisma.rampSession.update({
            where: { id: session.id },
            data: {
              status: 'FAILED',
              txStatus: 'failed',
              errorMessage: 'Blockchain transaction failed',
            },
          });

          rechecked++;
        }
      } catch (error) {
        console.error(`   ❌ Failed to recheck transaction ${session.id}:`, error);
      }
    }

    return rechecked;
  }

  /**
   * Repair invalid state transitions
   */
  static async repairInvalidStates() {
    let repaired = 0;

    // Check for sessions that skipped PAYMENT_CONFIRMED
    const invalidOnramps = await prisma.rampSession.findMany({
      where: {
        type: 'ONRAMP',
        status: 'CHAIN_PENDING',
        paymentStatus: null,
      },
    });

    for (const session of invalidOnramps) {
      console.log(`   🔧 Repairing invalid state: ${session.id} - CHAIN_PENDING without payment confirmation`);
      
      await prisma.rampSession.update({
        where: { id: session.id },
        data: {
          paymentStatus: 'assumed_paid',
          errorMessage: 'State repaired by reconciler',
        },
      });

      repaired++;
    }

    return repaired;
  }

  /**
   * Mark sessions that are too old as expired
   */
  static async markExpiredSessions() {
    const expiredThreshold = new Date(Date.now() - MAX_SESSION_AGE_MS);

    const result = await prisma.rampSession.updateMany({
      where: {
        status: {
          in: ['PENDING', 'AWAITING_PAYMENT'],
        },
        createdAt: {
          lt: expiredThreshold,
        },
      },
      data: {
        status: 'FAILED',
        errorMessage: 'Session expired after 24 hours',
      },
    });

    if (result.count > 0) {
      console.log(`   🕒 Marked ${result.count} expired sessions as FAILED`);
    }

    return result.count;
  }

  /**
   * Re-check payment status
   */
  static async recheckPayment(session) {
    try {
      const provider = getPaymentProvider();
      const status = await provider.getSessionStatus(session.paymentSessionId);

      if (status.status === 'paid') {
        await prisma.rampSession.update({
          where: { id: session.id },
          data: {
            status: 'PAYMENT_CONFIRMED',
            paymentStatus: 'paid',
            paymentIntentId: status.paymentIntentId,
          },
        });
      }
    } catch (error) {
      console.error(`Failed to recheck payment for ${session.id}:`, error);
    }
  }

  /**
   * Re-check blockchain transaction
   */
  static async recheckTransaction(session) {
    if (!isBlockchainConfigured()) {
      return;
    }

    try {
      const txStatus = await getTransactionStatus(session.txHash);

      if (txStatus.confirmed) {
        await prisma.rampSession.update({
          where: { id: session.id },
          data: {
            status: 'CHAIN_CONFIRMED',
            txStatus: 'confirmed',
            blockNumber: txStatus.blockNumber,
          },
        });

        await prisma.rampSession.update({
          where: { id: session.id },
          data: { status: 'COMPLETED' },
        });
      }
    } catch (error) {
      console.error(`Failed to recheck transaction for ${session.id}:`, error);
    }
  }

  /**
   * Log reconciliation statistics
   */
  static async logReconciliationStats(results) {
    try {
      await prisma.apiCallLog.create({
        data: {
          apiClientId: 'consistency-reconciler',
          endpoint: '/reconcile',
          method: 'RECONCILE',
          statusCode: 200,
          extraMeta: {
            cycle: reconciliationCount,
            timestamp: new Date().toISOString(),
            ...results,
          },
        },
      });
    } catch (error) {
      console.error('Failed to log reconciliation stats:', error);
    }
  }

  /**
   * Log reconciliation error
   */
  static async logReconciliationError(error) {
    try {
      await prisma.apiCallLog.create({
        data: {
          apiClientId: 'consistency-reconciler',
          endpoint: '/reconcile',
          method: 'ERROR',
          statusCode: 500,
          extraMeta: {
            cycle: reconciliationCount,
            timestamp: new Date().toISOString(),
            error: error.message,
            stack: error.stack,
          },
        },
      });
    } catch (logError) {
      console.error('Failed to log reconciliation error:', logError);
    }
  }
}

/**
 * Main loop
 */
async function reconcilerLoop() {
  console.log('🔍 Consistency Reconciler started');
  console.log(`   Interval: ${RECONCILE_INTERVAL_MS}ms`);
  console.log(`   Stuck threshold: ${STUCK_SESSION_THRESHOLD_MS}ms`);
  console.log(`   Max session age: ${MAX_SESSION_AGE_MS}ms`);

  while (isRunning) {
    await ConsistencyReconciler.run();
    await sleep(RECONCILE_INTERVAL_MS);
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Graceful shutdown
 */
async function shutdown() {
  console.log('\n🛑 Shutting down reconciler...');
  isRunning = false;
  await sleep(2000);
  await prisma.$disconnect();
  console.log('✅ Reconciler stopped');
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// Start reconciler
isRunning = true;
reconcilerLoop().catch((error) => {
  console.error('Fatal reconciler error:', error);
  process.exit(1);
});

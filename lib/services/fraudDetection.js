import { prisma } from '../prisma';

const MAX_TRANSACTION_AMOUNT = parseFloat(process.env.MAX_TRANSACTION_AMOUNT || '100000');
const MAX_DAILY_AMOUNT_PER_USER = parseFloat(process.env.MAX_DAILY_AMOUNT_PER_USER || '500000');
const FRAUD_CHECK_ENABLED = process.env.FRAUD_CHECK_ENABLED === 'true';

/**
 * Fraud detection rules engine
 */
export class FraudDetectionEngine {
  /**
   * Check transaction for fraud indicators
   */
  static async checkTransaction(rampSession, user) {
    if (!FRAUD_CHECK_ENABLED) {
      return { passed: true, flags: [] };
    }

    const flags = [];

    // Rule 1: Amount limit check
    const amountCheck = await this.checkAmountLimits(rampSession);
    if (!amountCheck.passed) {
      flags.push(...amountCheck.flags);
    }

    // Rule 2: Daily volume check per user
    if (user) {
      const volumeCheck = await this.checkDailyVolume(user.id, rampSession.amountFiat);
      if (!volumeCheck.passed) {
        flags.push(...volumeCheck.flags);
      }
    }

    // Rule 3: Velocity check (multiple transactions in short time)
    if (user) {
      const velocityCheck = await this.checkVelocity(user.id);
      if (!velocityCheck.passed) {
        flags.push(...velocityCheck.flags);
      }
    }

    // Rule 4: Wallet address blacklist check (placeholder)
    const walletCheck = await this.checkWalletBlacklist(rampSession.userWallet);
    if (!walletCheck.passed) {
      flags.push(...walletCheck.flags);
    }

    return {
      passed: flags.length === 0,
      flags,
      severity: this.calculateSeverity(flags),
    };
  }

  /**
   * Check amount limits
   */
  static async checkAmountLimits(rampSession) {
    const flags = [];
    const amount = parseFloat(rampSession.amountFiat);

    if (amount > MAX_TRANSACTION_AMOUNT) {
      flags.push({
        rule: 'AMOUNT_LIMIT_EXCEEDED',
        severity: 'HIGH',
        message: `Transaction amount €${amount} exceeds maximum €${MAX_TRANSACTION_AMOUNT}`,
        data: { amount, limit: MAX_TRANSACTION_AMOUNT },
      });
    }

    // Warn on suspiciously round numbers (potential test fraud)
    if (amount > 1000 && amount % 1000 === 0) {
      flags.push({
        rule: 'SUSPICIOUS_ROUND_AMOUNT',
        severity: 'LOW',
        message: 'Transaction uses suspiciously round number',
        data: { amount },
      });
    }

    return {
      passed: flags.filter((f) => f.severity === 'HIGH').length === 0,
      flags,
    };
  }

  /**
   * Check daily volume per user
   */
  static async checkDailyVolume(userId, newAmount) {
    const flags = [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    // Get all transactions for user today
    const apiClient = await prisma.apiClient.findFirst({
      where: { ownerId: userId },
      include: {
        rampSessions: {
          where: {
            createdAt: {
              gte: today,
            },
            status: {
              notIn: ['FAILED', 'REFUNDED'],
            },
          },
        },
      },
    });

    if (apiClient && apiClient.rampSessions) {
      const totalToday = apiClient.rampSessions.reduce(
        (sum, session) => sum + parseFloat(session.amountFiat),
        0
      );

      const projectedTotal = totalToday + parseFloat(newAmount);

      if (projectedTotal > MAX_DAILY_AMOUNT_PER_USER) {
        flags.push({
          rule: 'DAILY_VOLUME_EXCEEDED',
          severity: 'HIGH',
          message: `Daily volume €${projectedTotal} exceeds limit €${MAX_DAILY_AMOUNT_PER_USER}`,
          data: {
            current: totalToday,
            new: newAmount,
            projected: projectedTotal,
            limit: MAX_DAILY_AMOUNT_PER_USER,
          },
        });
      }
    }

    return {
      passed: flags.filter((f) => f.severity === 'HIGH').length === 0,
      flags,
    };
  }

  /**
   * Check transaction velocity (rapid successive transactions)
   */
  static async checkVelocity(userId) {
    const flags = [];
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000);

    const apiClient = await prisma.apiClient.findFirst({
      where: { ownerId: userId },
      include: {
        rampSessions: {
          where: {
            createdAt: {
              gte: fiveMinutesAgo,
            },
          },
        },
      },
    });

    if (apiClient && apiClient.rampSessions && apiClient.rampSessions.length >= 3) {
      flags.push({
        rule: 'HIGH_VELOCITY',
        severity: 'MEDIUM',
        message: `${apiClient.rampSessions.length} transactions in last 5 minutes`,
        data: { count: apiClient.rampSessions.length },
      });
    }

    return {
      passed: flags.filter((f) => f.severity === 'HIGH').length === 0,
      flags,
    };
  }

  /**
   * Check wallet blacklist (placeholder)
   */
  static async checkWalletBlacklist(walletAddress) {
    const flags = [];

    // Placeholder for blacklist check
    // In production, check against known fraudulent addresses
    // const blacklisted = await checkExternalBlacklist(walletAddress);

    return {
      passed: true,
      flags,
    };
  }

  /**
   * Calculate overall severity
   */
  static calculateSeverity(flags) {
    if (flags.some((f) => f.severity === 'HIGH')) return 'HIGH';
    if (flags.some((f) => f.severity === 'MEDIUM')) return 'MEDIUM';
    if (flags.length > 0) return 'LOW';
    return 'NONE';
  }

  /**
   * Log fraud check result
   */
  static async logFraudCheck(rampSessionId, result) {
    try {
      await prisma.apiCallLog.create({
        data: {
          apiClientId: 'fraud-detection',
          endpoint: '/fraud-check',
          method: 'CHECK',
          statusCode: result.passed ? 200 : 403,
          extraMeta: {
            rampSessionId,
            passed: result.passed,
            flags: result.flags,
            severity: result.severity,
            timestamp: new Date().toISOString(),
          },
        },
      });
    } catch (error) {
      console.error('Failed to log fraud check:', error);
    }
  }
}
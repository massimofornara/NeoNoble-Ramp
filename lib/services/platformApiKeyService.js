import crypto from 'crypto';
import { prisma } from '../prisma';
import { encryptSecret, decryptSecret } from '../utils/encryption';

/**
 * Platform API Key Service
 * Manages production API keys for external integrators
 * Secrets are ENCRYPTED (not hashed) to allow HMAC verification
 */

/**
 * Generate a platform API key (public identifier)
 */
export function generatePlatformApiKey() {
  const prefix = 'pk_';
  const randomBytes = crypto.randomBytes(24);
  return prefix + randomBytes.toString('hex');
}

/**
 * Generate a platform API secret
 */
export function generatePlatformApiSecret() {
  const prefix = 'sk_';
  const randomBytes = crypto.randomBytes(32);
  return prefix + randomBytes.toString('hex');
}

/**
 * Create a new platform API key
 */
export async function createPlatformApiKey({
  name,
  description = null,
  rateLimitDay = 10000,
  allowedIps = null,
  metadata = null,
  createdBy = null,
}) {
  const apiKey = generatePlatformApiKey();
  const apiSecret = generatePlatformApiSecret();
  const secretHash = encryptSecret(apiSecret); // Encrypt, not hash

  const key = await prisma.platformApiKey.create({
    data: {
      name,
      apiKey,
      secretHash, // Actually encrypted secret
      description,
      rateLimitDay,
      allowedIps,
      metadata,
      createdBy,
      status: 'ACTIVE',
    },
  });

  // Return the key with the secret ONLY ONCE
  return {
    ...key,
    apiSecret, // Only shown at creation time
    secretHash: undefined, // Never expose encrypted value
  };
}

/**
 * List all platform API keys (without secrets)
 */
export async function listPlatformApiKeys({ status = null } = {}) {
  const where = {};
  if (status) {
    where.status = status;
  }

  const keys = await prisma.platformApiKey.findMany({
    where,
    orderBy: {
      createdAt: 'desc',
    },
    select: {
      id: true,
      name: true,
      apiKey: true,
      status: true,
      rateLimitDay: true,
      dailyCalls: true,
      totalCalls: true,
      description: true,
      allowedIps: true,
      createdBy: true,
      createdAt: true,
      lastUsedAt: true,
      revokedAt: true,
      revokedBy: true,
      // Never return secretHash
    },
  });

  return keys;
}

/**
 * Get platform API key by public key
 */
export async function getPlatformApiKeyByKey(apiKey) {
  const key = await prisma.platformApiKey.findUnique({
    where: { apiKey },
  });

  return key;
}

/**
 * Verify platform API key credentials
 */
export async function verifyPlatformApiKey(apiKey, apiSecret) {
  const key = await getPlatformApiKeyByKey(apiKey);

  if (!key) {
    return { valid: false, error: 'API key not found' };
  }

  if (key.status !== 'ACTIVE') {
    return { valid: false, error: 'API key is not active' };
  }

  try {
    const decryptedSecret = decryptSecret(key.secretHash);
    const isValidSecret = decryptedSecret === apiSecret;

    if (!isValidSecret) {
      return { valid: false, error: 'Invalid secret' };
    }

    return { valid: true, key };
  } catch (error) {
    return { valid: false, error: 'Invalid secret' };
  }
}

/**
 * Revoke a platform API key
 */
export async function revokePlatformApiKey(id, revokedBy = null) {
  const key = await prisma.platformApiKey.update({
    where: { id },
    data: {
      status: 'REVOKED',
      revokedAt: new Date(),
      revokedBy,
    },
  });

  return key;
}

/**
 * Update platform API key usage stats
 */
export async function updatePlatformApiKeyUsage(apiKey) {
  const now = new Date();
  const key = await prisma.platformApiKey.findUnique({
    where: { apiKey },
  });

  if (!key) return;

  // Check if we need to reset daily counter
  const timeSinceReset = now.getTime() - key.lastResetAt.getTime();
  const dayInMs = 24 * 60 * 60 * 1000;

  if (timeSinceReset >= dayInMs) {
    // Reset daily counter
    await prisma.platformApiKey.update({
      where: { apiKey },
      data: {
        dailyCalls: 1,
        totalCalls: { increment: 1 },
        lastUsedAt: now,
        lastResetAt: now,
      },
    });
  } else {
    // Increment counters
    await prisma.platformApiKey.update({
      where: { apiKey },
      data: {
        dailyCalls: { increment: 1 },
        totalCalls: { increment: 1 },
        lastUsedAt: now,
      },
    });
  }
}

/**
 * Check rate limit for platform API key
 */
export async function checkPlatformApiKeyRateLimit(apiKey) {
  const key = await prisma.platformApiKey.findUnique({
    where: { apiKey },
  });

  if (!key) {
    return { allowed: false, reason: 'Key not found' };
  }

  if (key.status !== 'ACTIVE') {
    return { allowed: false, reason: 'Key not active' };
  }

  // Check if we need to reset
  const now = new Date();
  const timeSinceReset = now.getTime() - key.lastResetAt.getTime();
  const dayInMs = 24 * 60 * 60 * 1000;

  let currentDailyCalls = key.dailyCalls;

  if (timeSinceReset >= dayInMs) {
    currentDailyCalls = 0; // Will be reset on next update
  }

  if (currentDailyCalls >= key.rateLimitDay) {
    const resetTime = new Date(key.lastResetAt.getTime() + dayInMs);
    return {
      allowed: false,
      reason: 'Rate limit exceeded',
      limit: key.rateLimitDay,
      current: currentDailyCalls,
      resetAt: resetTime,
    };
  }

  return {
    allowed: true,
    limit: key.rateLimitDay,
    current: currentDailyCalls,
  };
}
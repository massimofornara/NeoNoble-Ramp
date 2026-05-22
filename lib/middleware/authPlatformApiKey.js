import { prisma } from '../prisma';
import { verifySignature } from '../utils/hmac';
import {
  getPlatformApiKeyByKey,
  updatePlatformApiKeyUsage,
  checkPlatformApiKeyRateLimit,
} from '../services/platformApiKeyService';
import { decryptSecret } from '../utils/encryption';

const TIMESTAMP_TOLERANCE_MS = 5 * 60 * 1000; // 5 minutes

/**
 * Platform API Key HMAC Authentication
 * For external integrators (e.g., NeoExchange)
 */
export async function authPlatformApiKey(request, bodyJson) {
  const apiKey = request.headers.get('x-api-key');
  const timestamp = request.headers.get('x-timestamp');
  const signature = request.headers.get('x-signature');

  // Validate required headers
  if (!apiKey) {
    return {
      ok: false,
      status: 401,
      body: {
        error: 'MISSING_API_KEY',
        message: 'X-API-KEY header is required',
      },
    };
  }

  if (!timestamp) {
    return {
      ok: false,
      status: 401,
      body: {
        error: 'MISSING_TIMESTAMP',
        message: 'X-TIMESTAMP header is required',
      },
    };
  }

  if (!signature) {
    return {
      ok: false,
      status: 401,
      body: {
        error: 'MISSING_SIGNATURE',
        message: 'X-SIGNATURE header is required',
      },
    };
  }

  // Find platform API key
  const key = await getPlatformApiKeyByKey(apiKey);

  if (!key) {
    await logPlatformAuthAttempt(null, 'INVALID_API_KEY', { apiKey: apiKey.substring(0, 10) + '...' });
    return {
      ok: false,
      status: 401,
      body: {
        error: 'INVALID_API_KEY',
        message: 'API key not found',
      },
    };
  }

  if (key.status !== 'ACTIVE') {
    await logPlatformAuthAttempt(key.id, 'API_KEY_NOT_ACTIVE');
    return {
      ok: false,
      status: 401,
      body: {
        error: 'API_KEY_DISABLED',
        message: 'API key is not active',
      },
    };
  }

  // Check rate limiting
  const rateLimitCheck = await checkPlatformApiKeyRateLimit(apiKey);
  if (!rateLimitCheck.allowed) {
    await logPlatformAuthAttempt(key.id, 'RATE_LIMIT_EXCEEDED');
    return {
      ok: false,
      status: 429,
      body: {
        error: 'RATE_LIMIT_EXCEEDED',
        message: `Rate limit exceeded. Daily limit: ${rateLimitCheck.limit}`,
        limit: rateLimitCheck.limit,
        current: rateLimitCheck.current,
        resetAt: rateLimitCheck.resetAt,
      },
    };
  }

  // Validate timestamp (replay protection)
  const requestTime = parseInt(timestamp, 10);
  const currentTime = Date.now();
  const timeDiff = Math.abs(currentTime - requestTime);

  if (timeDiff > TIMESTAMP_TOLERANCE_MS) {
    await logPlatformAuthAttempt(key.id, 'TIMESTAMP_EXPIRED', { timeDiff });
    return {
      ok: false,
      status: 401,
      body: {
        error: 'TIMESTAMP_EXPIRED',
        message: 'Request timestamp is outside the acceptable window (±5 minutes)',
      },
    };
  }

  // Decrypt secret and verify HMAC signature
  try {
    const apiSecret = decryptSecret(key.secretHash);
    const isValid = verifySignature(apiSecret, timestamp, bodyJson, signature);

    if (!isValid) {
      await logPlatformAuthAttempt(key.id, 'INVALID_SIGNATURE');
      return {
        ok: false,
        status: 401,
        body: {
          error: 'INVALID_SIGNATURE',
          message: 'HMAC signature verification failed',
        },
      };
    }
  } catch (error) {
    console.error('Signature verification error:', error);
    await logPlatformAuthAttempt(key.id, 'SIGNATURE_ERROR');
    return {
      ok: false,
      status: 500,
      body: {
        error: 'SIGNATURE_ERROR',
        message: 'Failed to verify signature',
      },
    };
  }

  // Log successful authentication
  await logPlatformAuthAttempt(key.id, 'SUCCESS');

  // Update usage statistics (async, don't wait)
  updatePlatformApiKeyUsage(apiKey).catch((err) =>
    console.error('Failed to update platform API key stats:', err)
  );

  return {
    ok: true,
    platformApiKey: key,
  };
}

/**
 * Log platform API key authentication attempt
 */
async function logPlatformAuthAttempt(keyId, result, metadata = {}) {
  try {
    await prisma.apiCallLog.create({
      data: {
        apiClientId: keyId || 'unknown',
        endpoint: '/auth/platform',
        method: 'AUTH',
        statusCode: result === 'SUCCESS' ? 200 : 401,
        extraMeta: {
          type: 'PLATFORM_API_KEY',
          result,
          timestamp: new Date().toISOString(),
          ...metadata,
        },
      },
    });
  } catch (error) {
    console.error('Failed to log platform auth attempt:', error);
  }
}
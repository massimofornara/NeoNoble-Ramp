import { prisma } from '../prisma';
import { verifySignature } from '../utils/hmac';

const TIMESTAMP_TOLERANCE_MS = 5 * 60 * 1000; // 5 minutes
const NONCE_EXPIRY_MS = 10 * 60 * 1000; // 10 minutes

/**
 * Enhanced HMAC authentication with nonce-based replay protection
 */
export async function authApiClientEnhanced(request, bodyJson) {
  const apiKey = request.headers.get('x-api-key');
  const timestamp = request.headers.get('x-timestamp');
  const signature = request.headers.get('x-signature');
  const nonce = request.headers.get('x-nonce'); // New: unique request identifier

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

  // Find API client
  const apiClient = await prisma.apiClient.findUnique({
    where: { apiKey },
  });

  if (!apiClient) {
    await logAuthAttempt(null, 'INVALID_API_KEY', { apiKey });
    return {
      ok: false,
      status: 401,
      body: {
        error: 'INVALID_API_KEY',
        message: 'API key not found',
      },
    };
  }

  if (apiClient.status !== 'ACTIVE') {
    await logAuthAttempt(apiClient.id, 'API_KEY_DISABLED');
    return {
      ok: false,
      status: 401,
      body: {
        error: 'API_KEY_DISABLED',
        message: 'API key is disabled',
      },
    };
  }

  // Check rate limiting
  const rateLimitCheck = await checkRateLimit(apiClient);
  if (!rateLimitCheck.allowed) {
    await logAuthAttempt(apiClient.id, 'RATE_LIMIT_EXCEEDED');
    return {
      ok: false,
      status: 429,
      body: {
        error: 'RATE_LIMIT_EXCEEDED',
        message: `Rate limit exceeded. Daily limit: ${apiClient.rateLimitDay}`,
        retryAfter: rateLimitCheck.retryAfter,
      },
    };
  }

  // Validate timestamp
  const requestTime = parseInt(timestamp, 10);
  const currentTime = Date.now();
  const timeDiff = Math.abs(currentTime - requestTime);

  if (timeDiff > TIMESTAMP_TOLERANCE_MS) {
    await logAuthAttempt(apiClient.id, 'TIMESTAMP_EXPIRED', { timeDiff });
    return {
      ok: false,
      status: 401,
      body: {
        error: 'TIMESTAMP_EXPIRED',
        message: 'Request timestamp is outside the acceptable window (±5 minutes)',
      },
    };
  }

  // Check nonce for replay protection (if provided)
  if (nonce) {
    const nonceCheck = await checkNonce(apiClient.id, nonce, timestamp);
    if (!nonceCheck.valid) {
      await logAuthAttempt(apiClient.id, 'NONCE_REPLAY_DETECTED', { nonce });
      return {
        ok: false,
        status: 401,
        body: {
          error: 'NONCE_ALREADY_USED',
          message: 'This nonce has already been used (replay attack detected)',
        },
      };
    }
  }

  // Verify HMAC signature
  const isValid = verifySignature(apiClient.apiSecret, timestamp, bodyJson, signature);

  if (!isValid) {
    await logAuthAttempt(apiClient.id, 'INVALID_SIGNATURE');
    return {
      ok: false,
      status: 401,
      body: {
        error: 'INVALID_SIGNATURE',
        message: 'HMAC signature verification failed',
      },
    };
  }

  // Log successful authentication
  await logAuthAttempt(apiClient.id, 'SUCCESS');

  // Update usage statistics (async, don't wait)
  updateClientUsage(apiClient.id).catch((err) =>
    console.error('Failed to update API client stats:', err)
  );

  return {
    ok: true,
    apiClient,
  };
}

/**
 * Check rate limiting for API client
 */
async function checkRateLimit(apiClient) {
  const now = new Date();
  const windowStart = new Date(apiClient.lastResetAt);
  const windowMs = parseInt(process.env.RATE_LIMIT_WINDOW_MS || '86400000', 10);
  
  // Check if we need to reset the window
  if (now - windowStart >= windowMs) {
    // Reset counter
    await prisma.apiClient.update({
      where: { id: apiClient.id },
      data: {
        dailyCalls: 0,
        lastResetAt: now,
      },
    });
    return { allowed: true };
  }

  // Check if within limit
  if (apiClient.dailyCalls >= apiClient.rateLimitDay) {
    const retryAfter = Math.ceil((windowStart.getTime() + windowMs - now.getTime()) / 1000);
    return {
      allowed: false,
      retryAfter,
    };
  }

  return { allowed: true };
}

/**
 * Check and store nonce to prevent replay attacks
 */
async function checkNonce(apiClientId, nonce, timestamp) {
  try {
    // Check if nonce already exists
    const existing = await prisma.nonce.findUnique({
      where: {
        apiClientId_nonce: {
          apiClientId,
          nonce,
        },
      },
    });

    if (existing) {
      return { valid: false, reason: 'nonce_reused' };
    }

    // Store nonce with expiry
    const expiresAt = new Date(Date.now() + NONCE_EXPIRY_MS);
    await prisma.nonce.create({
      data: {
        apiClientId,
        nonce,
        timestamp,
        expiresAt,
      },
    });

    // Clean up expired nonces (async, don't wait)
    cleanExpiredNonces().catch((err) => console.error('Failed to clean nonces:', err));

    return { valid: true };
  } catch (error) {
    console.error('Nonce check failed:', error);
    // On error, allow request but log warning
    return { valid: true, warning: 'nonce_check_failed' };
  }
}

/**
 * Clean up expired nonces
 */
async function cleanExpiredNonces() {
  const result = await prisma.nonce.deleteMany({
    where: {
      expiresAt: {
        lt: new Date(),
      },
    },
  });
  
  if (result.count > 0) {
    console.log(`Cleaned ${result.count} expired nonces`);
  }
}

/**
 * Update API client usage stats
 */
async function updateClientUsage(apiClientId) {
  await prisma.apiClient.update({
    where: { id: apiClientId },
    data: {
      totalCalls: { increment: 1 },
      dailyCalls: { increment: 1 },
      lastUsedAt: new Date(),
    },
  });
}

/**
 * Log authentication attempt
 */
async function logAuthAttempt(apiClientId, result, metadata = {}) {
  try {
    await prisma.apiCallLog.create({
      data: {
        apiClientId: apiClientId || 'unknown',
        endpoint: '/auth',
        method: 'AUTH',
        statusCode: result === 'SUCCESS' ? 200 : 401,
        extraMeta: {
          result,
          timestamp: new Date().toISOString(),
          ...metadata,
        },
      },
    });
  } catch (error) {
    console.error('Failed to log auth attempt:', error);
  }
}

/**
 * Log an API call
 */
export async function logApiCall(apiClientId, endpoint, method, statusCode, extraMeta = null) {
  try {
    await prisma.apiCallLog.create({
      data: {
        apiClientId: apiClientId || 'unknown',
        endpoint,
        method,
        statusCode,
        extraMeta,
      },
    });
  } catch (error) {
    console.error('Failed to log API call:', error);
  }
}

// Backward compatibility export
export { authApiClientEnhanced as authApiClient };
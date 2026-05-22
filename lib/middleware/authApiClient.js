import { prisma } from '../prisma';
import { verifySignature } from '../utils/hmac';

const TIMESTAMP_TOLERANCE_MS = 5 * 60 * 1000; // 5 minutes

/**
 * Middleware to authenticate API clients using HMAC signatures
 * Validates X-API-KEY, X-TIMESTAMP, and X-SIGNATURE headers
 */
export async function authApiClient(request, bodyJson) {
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

  // Find API client
  const apiClient = await prisma.apiClient.findUnique({
    where: { apiKey },
  });

  if (!apiClient) {
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
    return {
      ok: false,
      status: 401,
      body: {
        error: 'API_KEY_DISABLED',
        message: 'API key is disabled',
      },
    };
  }

  // Validate timestamp
  const requestTime = parseInt(timestamp, 10);
  const currentTime = Date.now();
  const timeDiff = Math.abs(currentTime - requestTime);

  if (timeDiff > TIMESTAMP_TOLERANCE_MS) {
    return {
      ok: false,
      status: 401,
      body: {
        error: 'TIMESTAMP_EXPIRED',
        message: 'Request timestamp is outside the acceptable window (±5 minutes)',
      },
    };
  }

  // Verify HMAC signature
  const isValid = verifySignature(apiClient.apiSecret, timestamp, bodyJson, signature);

  if (!isValid) {
    return {
      ok: false,
      status: 401,
      body: {
        error: 'INVALID_SIGNATURE',
        message: 'HMAC signature verification failed',
      },
    };
  }

  // Update usage statistics (async, don't wait)
  prisma.apiClient
    .update({
      where: { id: apiClient.id },
      data: {
        totalCalls: { increment: 1 },
        lastUsedAt: new Date(),
      },
    })
    .catch((err) => console.error('Failed to update API client stats:', err));

  return {
    ok: true,
    apiClient,
  };
}

/**
 * Log an API call
 */
export async function logApiCall(apiClientId, endpoint, method, statusCode, extraMeta = null) {
  try {
    await prisma.apiCallLog.create({
      data: {
        apiClientId,
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
import { NextResponse } from 'next/server';
import { authApiClient, logApiCall } from '@/lib/middleware/authApiClient';
import { calculateOfframpQuote } from '@/lib/services/rampService';

/**
 * POST /api/ramp-api-offramp-quote
 * Get a quote for selling tokens for fiat (HMAC-protected)
 */
export async function POST(request) {
  const endpoint = '/api/ramp-api-offramp-quote';
  const method = 'POST';

  try {
    // Read body
    const bodyText = await request.text();
    const body = bodyText ? JSON.parse(bodyText) : {};

    // Authenticate API client
    const auth = await authApiClient(request, bodyText || '{}');
    if (!auth.ok) {
      await logApiCall(null, endpoint, method, auth.status);
      return NextResponse.json(auth.body, { status: auth.status });
    }

    const { token, chain, tokens } = body;

    // Validate required fields
    if (!token || !chain || !tokens) {
      await logApiCall(auth.apiClient.id, endpoint, method, 400);
      return NextResponse.json(
        {
          error: 'MISSING_FIELDS',
          message: 'token, chain, and tokens are required',
        },
        { status: 400 }
      );
    }

    // Calculate quote
    const quote = calculateOfframpQuote({
      token,
      chain,
      tokens: parseFloat(tokens),
    });

    await logApiCall(auth.apiClient.id, endpoint, method, 200);

    return NextResponse.json(quote);
  } catch (error) {
    console.error('Offramp quote error:', error);
    return NextResponse.json(
      {
        error: 'QUOTE_FAILED',
        message: error.message || 'Failed to calculate quote',
      },
      { status: 400 }
    );
  }
}

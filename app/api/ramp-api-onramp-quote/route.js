import { NextResponse } from 'next/server';
import { authApiClient, logApiCall } from '@/lib/middleware/authApiClient';
import { calculateOnrampQuote } from '@/lib/services/rampService';

/**
 * POST /api/ramp-api-onramp-quote
 * Get a quote for buying tokens with fiat (HMAC-protected)
 */
export async function POST(request) {
  const endpoint = '/api/ramp-api-onramp-quote';
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

    const { fromFiat, toToken, chain, amountFiat } = body;

    // Validate required fields
    if (!fromFiat || !toToken || !chain || !amountFiat) {
      await logApiCall(auth.apiClient.id, endpoint, method, 400);
      return NextResponse.json(
        {
          error: 'MISSING_FIELDS',
          message: 'fromFiat, toToken, chain, and amountFiat are required',
        },
        { status: 400 }
      );
    }

    // Calculate quote
    const quote = calculateOnrampQuote({
      fromFiat,
      toToken,
      chain,
      amountFiat: parseFloat(amountFiat),
    });

    await logApiCall(auth.apiClient.id, endpoint, method, 200);

    return NextResponse.json(quote);
  } catch (error) {
    console.error('Onramp quote error:', error);
    return NextResponse.json(
      {
        error: 'QUOTE_FAILED',
        message: error.message || 'Failed to calculate quote',
      },
      { status: 400 }
    );
  }
}

import { NextResponse } from 'next/server';
import { requireAuth } from '@/lib/middleware/authJWT';
import { calculateOnrampQuote } from '@/lib/services/rampService';

/**
 * POST /api/ui-ramp-onramp-quote
 * Get onramp quote for normal users (JWT-protected)
 */
export async function POST(request) {
  const auth = await requireAuth(request);
  if (!auth.ok) {
    return NextResponse.json(auth.body, { status: auth.status });
  }

  try {
    const body = await request.json();
    const { fromFiat, toToken, chain, amountFiat } = body;

    // Validate required fields
    if (!fromFiat || !toToken || !chain || !amountFiat) {
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

    return NextResponse.json(quote);
  } catch (error) {
    console.error('UI onramp quote error:', error);
    return NextResponse.json(
      {
        error: 'QUOTE_FAILED',
        message: error.message || 'Failed to calculate quote',
      },
      { status: 400 }
    );
  }
}

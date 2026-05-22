import { NextResponse } from 'next/server';
import { requireAuth } from '@/lib/middleware/authJWT';
import { calculateOfframpQuote } from '@/lib/services/rampService';

/**
 * POST /api/ui-ramp-offramp-quote
 * Get offramp quote for normal users (JWT-protected)
 */
export async function POST(request) {
  const auth = await requireAuth(request);
  if (!auth.ok) {
    return NextResponse.json(auth.body, { status: auth.status });
  }

  try {
    const body = await request.json();
    const { token, chain, tokens } = body;

    // Validate required fields
    if (!token || !chain || !tokens) {
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

    return NextResponse.json(quote);
  } catch (error) {
    console.error('UI offramp quote error:', error);
    return NextResponse.json(
      {
        error: 'QUOTE_FAILED',
        message: error.message || 'Failed to calculate quote',
      },
      { status: 400 }
    );
  }
}

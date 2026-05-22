import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { authApiClient, logApiCall } from '@/lib/middleware/authApiClient';
import {
  calculateOfframpQuote,
  generateSessionId,
  generateCheckoutUrl,
} from '@/lib/services/rampService';

/**
 * POST /api/ramp-api-offramp
 * Create an offramp session (sell tokens for fiat) - HMAC-protected
 */
export async function POST(request) {
  const endpoint = '/api/ramp-api-offramp';
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

    const { token, chain, tokens, userWallet, payoutDestination } = body;

    // Validate required fields
    if (!token || !chain || !tokens || !userWallet || !payoutDestination) {
      await logApiCall(auth.apiClient.id, endpoint, method, 400);
      return NextResponse.json(
        {
          error: 'MISSING_FIELDS',
          message: 'token, chain, tokens, userWallet, and payoutDestination are required',
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

    // Generate session
    const sessionId = generateSessionId();
    const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000';
    const checkoutUrl = generateCheckoutUrl(sessionId, baseUrl);

    // Create ramp session
    const rampSession = await prisma.rampSession.create({
      data: {
        id: sessionId,
        apiClientId: auth.apiClient.id,
        type: 'OFFRAMP',
        tokenSymbol: token,
        chain,
        amountFiat: quote.amountFiat,
        tokens: quote.tokens,
        feeBase: quote.feeBase,
        status: 'PENDING',
        checkoutUrl,
        userWallet,
        payoutDestination,
      },
    });

    // Update total fee
    await prisma.apiClient.update({
      where: { id: auth.apiClient.id },
      data: {
        totalFeeBase: {
          increment: quote.feeBase,
        },
      },
    });

    await logApiCall(auth.apiClient.id, endpoint, method, 201);

    return NextResponse.json(
      {
        sessionId: rampSession.id,
        status: rampSession.status,
        checkoutUrl: rampSession.checkoutUrl,
        details: {
          type: 'OFFRAMP',
          token,
          chain,
          tokens: quote.tokens,
          amountFiat: quote.amountFiat,
          feeBase: quote.feeBase,
          rate: quote.rate,
          payoutDestination,
        },
      },
      { status: 201 }
    );
  } catch (error) {
    console.error('Offramp session error:', error);
    return NextResponse.json(
      {
        error: 'SESSION_FAILED',
        message: error.message || 'Failed to create offramp session',
      },
      { status: 400 }
    );
  }
}

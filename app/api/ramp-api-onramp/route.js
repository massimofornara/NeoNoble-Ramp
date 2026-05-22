import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { authApiClient, logApiCall } from '@/lib/middleware/authApiClient';
import {
  calculateOnrampQuote,
  generateSessionId,
  generateCheckoutUrl,
} from '@/lib/services/rampService';

/**
 * POST /api/ramp-api-onramp
 * Create an onramp session (buy tokens with fiat) - HMAC-protected
 */
export async function POST(request) {
  const endpoint = '/api/ramp-api-onramp';
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

    const { fromFiat, toToken, chain, amountFiat, userWallet } = body;

    // Validate required fields
    if (!fromFiat || !toToken || !chain || !amountFiat || !userWallet) {
      await logApiCall(auth.apiClient.id, endpoint, method, 400);
      return NextResponse.json(
        {
          error: 'MISSING_FIELDS',
          message: 'fromFiat, toToken, chain, amountFiat, and userWallet are required',
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

    // Generate session
    const sessionId = generateSessionId();
    const baseUrl = process.env.NEXT_PUBLIC_BASE_URL || 'http://localhost:3000';
    const checkoutUrl = generateCheckoutUrl(sessionId, baseUrl);

    // Create ramp session
    const rampSession = await prisma.rampSession.create({
      data: {
        id: sessionId,
        apiClientId: auth.apiClient.id,
        type: 'ONRAMP',
        tokenSymbol: toToken,
        chain,
        amountFiat: quote.amountFiat,
        tokens: quote.estimatedTokens,
        feeBase: quote.feeBase,
        status: 'PENDING',
        checkoutUrl,
        userWallet,
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
          type: 'ONRAMP',
          token: toToken,
          chain,
          amountFiat: quote.amountFiat,
          estimatedTokens: quote.estimatedTokens,
          feeBase: quote.feeBase,
          rate: quote.rate,
        },
      },
      { status: 201 }
    );
  } catch (error) {
    console.error('Onramp session error:', error);
    return NextResponse.json(
      {
        error: 'SESSION_FAILED',
        message: error.message || 'Failed to create onramp session',
      },
      { status: 400 }
    );
  }
}

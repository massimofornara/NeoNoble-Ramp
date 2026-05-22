import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { requireAuth } from '@/lib/middleware/authJWT';
import {
  calculateOnrampQuote,
  generateSessionId,
  generateCheckoutUrl,
} from '@/lib/services/rampService';

/**
 * POST /api/ui-ramp-onramp
 * Create onramp session for normal users (JWT-protected)
 * Uses internal platform_internal API client
 */
export async function POST(request) {
  const auth = await requireAuth(request);
  if (!auth.ok) {
    return NextResponse.json(auth.body, { status: auth.status });
  }

  try {
    const body = await request.json();
    const { fromFiat, toToken, chain, amountFiat, userWallet } = body;

    // Validate required fields
    if (!fromFiat || !toToken || !chain || !amountFiat || !userWallet) {
      return NextResponse.json(
        {
          error: 'MISSING_FIELDS',
          message: 'fromFiat, toToken, chain, amountFiat, and userWallet are required',
        },
        { status: 400 }
      );
    }

    // Get or create platform_internal API client
    let platformClient = await prisma.apiClient.findFirst({
      where: { name: 'platform_internal' },
    });

    if (!platformClient) {
      return NextResponse.json(
        {
          error: 'PLATFORM_CLIENT_NOT_FOUND',
          message: 'Platform internal API client not configured',
        },
        { status: 500 }
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
        apiClientId: platformClient.id,
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

    // Update platform client stats
    await prisma.apiClient.update({
      where: { id: platformClient.id },
      data: {
        totalCalls: { increment: 1 },
        totalFeeBase: { increment: quote.feeBase },
        lastUsedAt: new Date(),
      },
    });

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
    console.error('UI onramp session error:', error);
    return NextResponse.json(
      {
        error: 'SESSION_FAILED',
        message: error.message || 'Failed to create onramp session',
      },
      { status: 400 }
    );
  }
}

import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { requireAuth } from '@/lib/middleware/authJWT';
import {
  calculateOfframpQuote,
  generateSessionId,
  generateCheckoutUrl,
} from '@/lib/services/rampService';

/**
 * POST /api/ui-ramp-offramp
 * Create offramp session for normal users (JWT-protected)
 * Uses internal platform_internal API client
 */
export async function POST(request) {
  const auth = await requireAuth(request);
  if (!auth.ok) {
    return NextResponse.json(auth.body, { status: auth.status });
  }

  try {
    const body = await request.json();
    const { token, chain, tokens, userWallet, payoutDestination } = body;

    // Validate required fields
    if (!token || !chain || !tokens || !userWallet || !payoutDestination) {
      return NextResponse.json(
        {
          error: 'MISSING_FIELDS',
          message: 'token, chain, tokens, userWallet, and payoutDestination are required',
        },
        { status: 400 }
      );
    }

    // Get platform_internal API client
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
        apiClientId: platformClient.id,
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
    console.error('UI offramp session error:', error);
    return NextResponse.json(
      {
        error: 'SESSION_FAILED',
        message: error.message || 'Failed to create offramp session',
      },
      { status: 400 }
    );
  }
}

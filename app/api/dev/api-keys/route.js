import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { requireAuth } from '@/lib/middleware/authJWT';
import { generateApiKey, generateApiSecret } from '@/lib/utils/apiKeys';

/**
 * GET /api/dev/api-keys
 * List all API keys for the authenticated user
 */
export async function GET(request) {
  const auth = await requireAuth(request);
  if (!auth.ok) {
    return NextResponse.json(auth.body, { status: auth.status });
  }

  try {
    const apiClients = await prisma.apiClient.findMany({
      where: {
        ownerId: auth.user.id,
      },
      orderBy: {
        createdAt: 'desc',
      },
      select: {
        id: true,
        name: true,
        apiKey: true,
        status: true,
        rateLimitDay: true,
        totalCalls: true,
        totalFeeBase: true,
        createdAt: true,
        lastUsedAt: true,
      },
    });

    return NextResponse.json({
      apiClients,
    });
  } catch (error) {
    console.error('Failed to fetch API keys:', error);
    return NextResponse.json(
      { error: 'FETCH_FAILED', message: 'Failed to fetch API keys' },
      { status: 500 }
    );
  }
}

/**
 * POST /api/dev/api-keys
 * Create a new API key for the authenticated user
 */
export async function POST(request) {
  const auth = await requireAuth(request);
  if (!auth.ok) {
    return NextResponse.json(auth.body, { status: auth.status });
  }

  try {
    const body = await request.json();
    const { name } = body;

    if (!name) {
      return NextResponse.json(
        { error: 'NAME_REQUIRED', message: 'API client name is required' },
        { status: 400 }
      );
    }

    // Generate credentials
    const apiKey = generateApiKey();
    const apiSecret = generateApiSecret();

    // Create API client
    const apiClient = await prisma.apiClient.create({
      data: {
        ownerId: auth.user.id,
        name,
        apiKey,
        apiSecret,
        status: 'ACTIVE',
      },
    });

    return NextResponse.json(
      {
        message: 'API key created successfully',
        apiClient: {
          id: apiClient.id,
          name: apiClient.name,
          apiKey: apiClient.apiKey,
          apiSecret: apiClient.apiSecret, // Only shown once!
          status: apiClient.status,
          createdAt: apiClient.createdAt,
        },
        warning: 'Store the API secret securely. It will not be shown again.',
      },
      { status: 201 }
    );
  } catch (error) {
    console.error('Failed to create API key:', error);
    return NextResponse.json(
      { error: 'CREATE_FAILED', message: 'Failed to create API key' },
      { status: 500 }
    );
  }
}

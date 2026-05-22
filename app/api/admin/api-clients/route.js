import { NextResponse } from 'next/server';
import bcrypt from 'bcryptjs';
import { prisma } from '@/lib/prisma';
import { requireAdmin } from '@/lib/middleware/authJWT';
import { generateApiKey, generateApiSecret } from '@/lib/utils/apiKeys';

/**
 * GET /api/admin/api-clients
 * List all API clients (admin only)
 */
export async function GET(request) {
  const auth = await requireAdmin(request);
  if (!auth.ok) {
    return NextResponse.json(auth.body, { status: auth.status });
  }

  try {
    const { searchParams } = new URL(request.url);
    const page = parseInt(searchParams.get('page') || '1', 10);
    const limit = parseInt(searchParams.get('limit') || '50', 10);
    const skip = (page - 1) * limit;

    const [apiClients, total] = await Promise.all([
      prisma.apiClient.findMany({
        skip,
        take: limit,
        orderBy: {
          createdAt: 'desc',
        },
        include: {
          owner: {
            select: {
              email: true,
              role: true,
            },
          },
        },
      }),
      prisma.apiClient.count(),
    ]);

    return NextResponse.json({
      apiClients,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
      },
    });
  } catch (error) {
    console.error('Failed to fetch API clients:', error);
    return NextResponse.json(
      { error: 'FETCH_FAILED', message: 'Failed to fetch API clients' },
      { status: 500 }
    );
  }
}

/**
 * POST /api/admin/api-clients
 * Create an API client for a user (admin only)
 */
export async function POST(request) {
  const auth = await requireAdmin(request);
  if (!auth.ok) {
    return NextResponse.json(auth.body, { status: auth.status });
  }

  try {
    const body = await request.json();
    const { ownerEmail, name } = body;

    if (!ownerEmail || !name) {
      return NextResponse.json(
        { error: 'MISSING_FIELDS', message: 'ownerEmail and name are required' },
        { status: 400 }
      );
    }

    // Find or create user
    let user = await prisma.user.findUnique({
      where: { email: ownerEmail },
    });

    if (!user) {
      // Create user with random password
      const randomPassword = generateApiSecret().substring(0, 16);
      const passwordHash = await bcrypt.hash(randomPassword, 10);

      user = await prisma.user.create({
        data: {
          email: ownerEmail,
          passwordHash,
          role: 'USER',
        },
      });
    }

    // Generate credentials
    const apiKey = generateApiKey();
    const apiSecret = generateApiSecret();

    // Create API client
    const apiClient = await prisma.apiClient.create({
      data: {
        ownerId: user.id,
        name,
        apiKey,
        apiSecret,
        status: 'ACTIVE',
      },
    });

    return NextResponse.json(
      {
        message: 'API client created successfully',
        apiClient: {
          id: apiClient.id,
          name: apiClient.name,
          apiKey: apiClient.apiKey,
          apiSecret: apiClient.apiSecret,
          status: apiClient.status,
          createdAt: apiClient.createdAt,
          owner: {
            email: user.email,
          },
        },
        warning: 'Store the API secret securely. It will not be shown again.',
      },
      { status: 201 }
    );
  } catch (error) {
    console.error('Failed to create API client:', error);
    return NextResponse.json(
      { error: 'CREATE_FAILED', message: 'Failed to create API client' },
      { status: 500 }
    );
  }
}

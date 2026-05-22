import crypto from 'crypto';
import jwt from 'jsonwebtoken';
import type { NextRequest } from 'next/server';
import type { TransakWebhookData, TransakWebhookEnvelope } from '@/types/transak';
import { requireServerTransakConfig } from '@/lib/transak/config';
import { getRedis } from '@/lib/transak/redis';

export function getRequestIp(request: NextRequest) {
  return (
    request.headers.get('cf-connecting-ip') ||
    request.headers.get('x-real-ip') ||
    request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ||
    'unknown'
  );
}

export function hashIp(ip: string) {
  return crypto.createHash('sha256').update(ip).digest('hex');
}

export function assertAllowedOrigin(request: NextRequest) {
  const { allowedOrigins } = requireServerTransakConfig();
  const origin = request.headers.get('origin');
  if (!origin) return;
  if (allowedOrigins.includes('*')) return;
  if (!allowedOrigins.includes(origin)) {
    throw new Error(`Origin not allowed: ${origin}`);
  }
}

export function assertTransakWebhookIp(request: NextRequest) {
  const allowlist = (process.env.TRANSAK_WEBHOOK_IP_ALLOWLIST || '')
    .split(',')
    .map((ip) => ip.trim())
    .filter(Boolean);
  if (allowlist.length === 0) return;
  const ip = getRequestIp(request);
  if (!allowlist.includes(ip)) {
    throw new Error(`Transak webhook IP not allowed: ${ip}`);
  }
}

export function verifyOptionalHmac(rawBody: string, request: NextRequest) {
  const signature =
    request.headers.get('x-transak-signature') ||
    request.headers.get('transak-signature') ||
    request.headers.get('x-signature');
  const secret = process.env.TRANSAK_WEBHOOK_SECRET;
  if (!signature || !secret) return;
  const expected = crypto.createHmac('sha256', secret).update(rawBody).digest('hex');
  const provided = signature.replace(/^sha256=/, '');
  if (
    expected.length !== provided.length ||
    !crypto.timingSafeEqual(Buffer.from(expected, 'hex'), Buffer.from(provided, 'hex'))
  ) {
    throw new Error('Invalid Transak webhook HMAC signature');
  }
}

export async function rateLimit(input: {
  key: string;
  limit: number;
  windowSeconds: number;
}) {
  const redis = getRedis();
  if (!redis) return { allowed: true, remaining: input.limit - 1 };

  const redisKey = `ratelimit:${input.key}`;
  const count = await redis.incr(redisKey);
  if (count === 1) await redis.expire(redisKey, input.windowSeconds);

  return {
    allowed: count <= input.limit,
    remaining: Math.max(0, input.limit - count),
  };
}

export async function assertWebhookNotReplayed(eventId: string) {
  const redis = getRedis();
  if (!redis) return false;
  const key = `transak:webhook:event:${eventId}`;
  const inserted = await redis.set(key, '1', 'EX', 60 * 60 * 24 * 7, 'NX');
  if (!inserted) {
    throw new Error(`Replay detected for webhook event ${eventId}`);
  }
  return false;
}

export function verifyTransakWebhook(envelope: TransakWebhookEnvelope): TransakWebhookData {
  const { accessToken, webhookSecret } = requireServerTransakConfig();
  const secret = accessToken || webhookSecret;
  if (envelope.data && typeof envelope.data === 'object' && 'eventID' in envelope.data) {
    return envelope.data as TransakWebhookData;
  }
  if (!envelope.data || typeof envelope.data !== 'string') {
    throw new Error('Transak webhook payload is missing signed data');
  }
  if (!secret) {
    throw new Error('TRANSAK_ACCESS_TOKEN is required to verify Transak signed webhook data');
  }

  const decoded = jwt.verify(envelope.data, secret, {
    algorithms: ['HS256'],
  }) as TransakWebhookData;

  return decoded;
}

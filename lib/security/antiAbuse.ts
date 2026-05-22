import { slidingWindowLimit } from '@/lib/security/rateLimiter';

export async function evaluateAntiAbuse(input: {
  ip: string;
  userAgent?: string;
  userId?: string;
  action: string;
}) {
  const reasons: string[] = [];
  let score = 0;
  if (!input.userAgent || input.userAgent.length < 12) {
    score += 20;
    reasons.push('missing_or_short_user_agent');
  }
  const ipLimit = await slidingWindowLimit({ subject: input.ip, action: input.action, limit: 120, windowMs: 60_000 });
  if (!ipLimit.allowed) {
    score += 70;
    reasons.push('ip_rate_limit');
  }
  if (input.userId) {
    const userLimit = await slidingWindowLimit({ subject: input.userId, action: input.action, limit: 60, windowMs: 60_000 });
    if (!userLimit.allowed) {
      score += 60;
      reasons.push('user_rate_limit');
    }
  }
  return { allowed: score < 70, score, reasons };
}

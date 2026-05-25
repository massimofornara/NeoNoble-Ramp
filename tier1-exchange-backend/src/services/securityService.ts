import { createHmac, randomBytes, randomUUID } from "node:crypto";
import { join } from "node:path";
import type { IncomingHttpHeaders } from "node:http";
import { atomicWriteJson, readJsonFile } from "../core/persistence.js";
import type { ReplayNonceStore } from "../core/store.js";

interface SigningKey {
  kid: string;
  secret: string;
  active: boolean;
  createdAt: string;
}

export class SecurityService {
  private readonly requests = new Map<string, number[]>();
  private readonly windowMs = Number(process.env.API_RATE_LIMIT_WINDOW_MS ?? 60_000);
  private readonly maxRequests = Number(process.env.API_RATE_LIMIT_MAX ?? 10_000);
  private readonly webhookToleranceMs = Number(process.env.WEBHOOK_REPLAY_TOLERANCE_MS ?? 300_000);

  constructor(
    private readonly keyFile: string,
    private readonly webhookNonces: ReplayNonceStore,
  ) {
    this.ensureKey();
  }

  assertRateLimit(identity: string): void {
    if (this.maxRequests <= 0) return;
    const now = Date.now();
    const recent = (this.requests.get(identity) ?? []).filter((time) => now - time <= this.windowMs);
    if (recent.length >= this.maxRequests) {
      throw new Error("API rate limit exceeded");
    }
    recent.push(now);
    this.requests.set(identity, recent);
  }

  async assertWebhookReplayProtection(headers: IncomingHttpHeaders): Promise<{ timestamp: string; nonce: string }> {
    const timestamp = String(headers["x-provider-timestamp"] ?? "");
    const nonce = String(headers["x-provider-nonce"] ?? "");
    if (!timestamp || !nonce) throw new Error("Missing webhook timestamp or nonce");
    const parsed = Date.parse(timestamp);
    if (!Number.isFinite(parsed) || Math.abs(Date.now() - parsed) > this.webhookToleranceMs) {
      throw new Error("Webhook timestamp is outside replay tolerance");
    }
    if (this.webhookNonces.has(nonce)) {
      throw new Error("Webhook nonce has already been used");
    }
    await this.webhookNonces.remember(nonce);
    return { timestamp, nonce };
  }

  rotateJwtSigningKey(): { kid: string; active: boolean; createdAt: string } {
    const keys = this.keys().map((key) => ({ ...key, active: false }));
    const next: SigningKey = {
      kid: randomUUID(),
      secret: randomBytes(32).toString("base64url"),
      active: true,
      createdAt: new Date().toISOString(),
    };
    atomicWriteJson(this.keyFile, [...keys, next]);
    return { kid: next.kid, active: true, createdAt: next.createdAt };
  }

  signJwt(payload: Record<string, unknown>): string {
    const key = this.activeKey();
    const header = base64UrlJson({ alg: "HS256", typ: "JWT", kid: key.kid });
    const body = base64UrlJson({ ...payload, iat: Math.floor(Date.now() / 1000) });
    const signature = createHmac("sha256", key.secret).update(`${header}.${body}`).digest("base64url");
    return `${header}.${body}.${signature}`;
  }

  status(): Record<string, unknown> {
    return {
      activeKid: this.activeKey().kid,
      keyCount: this.keys().length,
      rateLimit: {
        windowMs: this.windowMs,
        maxRequests: this.maxRequests,
        mode: this.maxRequests <= 0 ? "disabled" : "security-only",
      },
      webhookReplayToleranceMs: this.webhookToleranceMs,
    };
  }

  private ensureKey(): void {
    if (this.keys().length === 0) {
      this.rotateJwtSigningKey();
    }
  }

  private activeKey(): SigningKey {
    const key = this.keys().find((candidate) => candidate.active);
    if (!key) throw new Error("No active JWT signing key");
    return key;
  }

  private keys(): SigningKey[] {
    return readJsonFile<SigningKey[]>(this.keyFile || join(".", "security-keys.json"), []);
  }
}

function base64UrlJson(value: Record<string, unknown>): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

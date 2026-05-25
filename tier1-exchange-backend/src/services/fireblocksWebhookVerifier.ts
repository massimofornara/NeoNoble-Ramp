import { createHash, createHmac, createPublicKey, timingSafeEqual, verify as verifySignature, type JsonWebKey } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import type { IncomingHttpHeaders } from "node:http";
import type { ReplayNonceStore } from "../core/store.js";

interface JwksKey {
  kty: string;
  kid: string;
  use?: string;
  alg?: string;
  n: string;
  e: string;
}

export interface FireblocksWebhookVerification {
  method: "jwks-detached-jws" | "legacy-rsa" | "shared-secret";
  replayKey: string;
}

export class FireblocksWebhookVerifier {
  private jwksCache?: { expiresAt: number; keys: JwksKey[] };

  constructor(private readonly nonces: ReplayNonceStore) {}

  async verify(rawBody: string, headers: IncomingHttpHeaders): Promise<FireblocksWebhookVerification> {
    const result = await this.verifyAuthenticity(rawBody, headers);
    if (this.nonces.has(result.replayKey)) {
      throw new Error("Fireblocks webhook replay detected");
    }
    await this.nonces.remember(result.replayKey);
    return result;
  }

  private async verifyAuthenticity(rawBody: string, headers: IncomingHttpHeaders): Promise<FireblocksWebhookVerification> {
    const detachedJws = headerValue(headers, "fireblocks-webhook-signature");
    if (detachedJws) {
      await this.verifyDetachedJws(rawBody, detachedJws);
      return { method: "jwks-detached-jws", replayKey: replayKey(headers, rawBody) };
    }

    const legacySignature = headerValue(headers, "fireblocks-signature");
    if (legacySignature && process.env.FIREBLOCKS_WEBHOOK_PUBLIC_KEY_PATH) {
      this.verifyLegacySignature(rawBody, legacySignature, process.env.FIREBLOCKS_WEBHOOK_PUBLIC_KEY_PATH);
      return { method: "legacy-rsa", replayKey: replayKey(headers, rawBody) };
    }

    const secret = process.env.FIREBLOCKS_WEBHOOK_SECRET;
    if (secret) {
      this.verifySharedSecret(rawBody, headers, secret);
      return { method: "shared-secret", replayKey: replayKey(headers, rawBody) };
    }

    throw new Error("Missing Fireblocks webhook signature. Configure JWKS verification or FIREBLOCKS_WEBHOOK_SECRET for an internal webhook relay.");
  }

  private async verifyDetachedJws(rawBody: string, signature: string): Promise<void> {
    const parts = signature.split(".");
    if (parts.length !== 3 || parts[1] !== "") {
      throw new Error("Invalid Fireblocks detached JWS format");
    }
    const [encodedHeader, , encodedSignature] = parts;
    const header = JSON.parse(Buffer.from(encodedHeader, "base64url").toString("utf8")) as { kid?: string; alg?: string };
    if (header.alg !== "RS512") {
      throw new Error(`Unsupported Fireblocks webhook JWS alg: ${header.alg ?? "missing"}`);
    }
    if (!header.kid) throw new Error("Fireblocks webhook JWS missing kid");
    const jwk = (await this.jwks()).find((key) => key.kid === header.kid);
    if (!jwk) throw new Error(`Fireblocks webhook JWS kid not found in JWKS: ${header.kid}`);
    const publicKey = createPublicKey({ key: jwk as unknown as JsonWebKey, format: "jwk" });
    const signingInput = `${encodedHeader}.${Buffer.from(rawBody).toString("base64url")}`;
    const valid = verifySignature("RSA-SHA512", Buffer.from(signingInput), publicKey, Buffer.from(encodedSignature, "base64url"));
    if (!valid) throw new Error("Invalid Fireblocks webhook detached JWS signature");
  }

  private verifyLegacySignature(rawBody: string, signature: string, publicKeyPath: string): void {
    if (!existsSync(publicKeyPath)) throw new Error("FIREBLOCKS_WEBHOOK_PUBLIC_KEY_PATH is not readable");
    const publicKey = readFileSync(publicKeyPath, "utf8");
    const digest = createHash("sha512").update(rawBody).digest();
    const valid = verifySignature("RSA-SHA512", digest, publicKey, Buffer.from(signature, "base64"));
    if (!valid) throw new Error("Invalid Fireblocks legacy webhook signature");
  }

  private verifySharedSecret(rawBody: string, headers: IncomingHttpHeaders, secret: string): void {
    const directSecret = headerValue(headers, "x-fireblocks-webhook-secret") ?? headerValue(headers, "x-webhook-secret");
    if (directSecret && timingSafeTextEqual(directSecret, secret)) return;
    const signature = headerValue(headers, "x-provider-signature") ?? headerValue(headers, "x-fireblocks-signature");
    if (!signature) throw new Error("Missing Fireblocks shared-secret signature");
    const timestamp = headerValue(headers, "x-provider-timestamp");
    const nonce = headerValue(headers, "x-provider-nonce");
    const signedPayload = timestamp && nonce ? `${timestamp}.${nonce}.${rawBody}` : rawBody;
    const expected = createHmac("sha256", secret).update(signedPayload).digest("hex");
    if (!timingSafeTextEqual(signature, expected)) {
      throw new Error("Invalid Fireblocks shared-secret webhook signature");
    }
  }

  private async jwks(): Promise<JwksKey[]> {
    const now = Date.now();
    if (this.jwksCache && this.jwksCache.expiresAt > now) return this.jwksCache.keys;
    const url = process.env.FIREBLOCKS_WEBHOOK_JWKS_URL || jwksUrlFor(process.env.FIREBLOCKS_BASE_URL ?? "");
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Fireblocks JWKS fetch failed: ${response.status}`);
    const body = (await response.json()) as { keys?: JwksKey[] };
    const keys = Array.isArray(body.keys) ? body.keys : [];
    this.jwksCache = { keys, expiresAt: now + 60 * 60 * 1000 };
    return keys;
  }
}

function headerValue(headers: IncomingHttpHeaders, name: string): string | undefined {
  const value = headers[name.toLowerCase()];
  if (Array.isArray(value)) return value[0];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function replayKey(headers: IncomingHttpHeaders, rawBody: string): string {
  return (
    headerValue(headers, "fireblocks-webhook-id") ??
    headerValue(headers, "x-provider-nonce") ??
    createHash("sha256").update(rawBody).digest("hex")
  );
}

function jwksUrlFor(baseUrl: string): string {
  if (/sandbox/i.test(baseUrl)) return "https://sandbox-keys.fireblocks.io/.well-known/jwks.json";
  if (/eu2/i.test(baseUrl)) return "https://eu2-keys.fireblocks.io/.well-known/jwks.json";
  if (/eu/i.test(baseUrl)) return "https://eu-keys.fireblocks.io/.well-known/jwks.json";
  return "https://keys.fireblocks.io/.well-known/jwks.json";
}

function timingSafeTextEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

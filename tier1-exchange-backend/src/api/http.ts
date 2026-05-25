import type { IncomingMessage, ServerResponse } from "node:http";

export async function readJson<T>(request: IncomingMessage): Promise<T> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  const rawBody = Buffer.concat(chunks).toString("utf8");
  return rawBody ? (JSON.parse(rawBody) as T) : ({} as T);
}

export async function readRawBody(request: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf8");
}

export function sendJson(response: ServerResponse, statusCode: number, body: unknown): void {
  response.writeHead(statusCode, {
    "content-type": "application/json",
  });
  response.end(JSON.stringify(body, null, 2));
}

export function requireIdempotencyKey(headers: IncomingMessage["headers"], body: Record<string, unknown>): string {
  const key = headers["idempotency-key"] || body.idempotencyKey;
  if (!key || Array.isArray(key) || String(key).trim().length < 8) {
    throw new Error("idempotencyKey is required on all mutation endpoints");
  }
  return String(key);
}

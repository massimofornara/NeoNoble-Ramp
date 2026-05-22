import { createHmac, randomUUID } from "node:crypto";
import { TerminalRail } from "../services/terminal-rail.js";

export class SignedHttpClient {
  constructor({ name, baseUrl, apiKey, secret, timeoutMs = 10000, requireConfigured = false, eventBus }) {
    this.name = name;
    this.baseUrl = baseUrl;
    this.apiKey = apiKey;
    this.secret = secret;
    this.timeoutMs = timeoutMs;
    this.requireConfigured = requireConfigured;
    this.terminalRail = new TerminalRail({ name, secret: secret ?? `${name}-terminal-key`, eventBus });
  }

  configured() {
    return Boolean(this.baseUrl && this.apiKey && this.secret);
  }

  async request(method, path, body = {}) {
    if (!this.configured()) {
      if (this.requireConfigured) {
        throw new Error(`${this.name} adapter is not configured for live execution`);
      }
      return this.terminalRail.createInstruction({ method, path, payload: body });
    }
    const payload = JSON.stringify(body);
    const timestamp = new Date().toISOString();
    const idempotencyKey = body.idempotencyKey ?? randomUUID();
    const signaturePayload = `${method}\n${path}\n${timestamp}\n${idempotencyKey}\n${payload}`;
    const signature = createHmac("sha256", this.secret).update(signaturePayload).digest("hex");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await fetch(new URL(path, this.baseUrl), {
        method,
        signal: controller.signal,
        headers: {
          "content-type": "application/json",
          "x-api-key": this.apiKey,
          "x-signature": signature,
          "x-timestamp": timestamp,
          "idempotency-key": idempotencyKey
        },
        body: method === "GET" ? undefined : payload
      });
      const responseBody = await response.text();
      const parsed = responseBody ? JSON.parse(responseBody) : {};
      if (!response.ok) throw new Error(`${this.name} ${response.status}: ${responseBody}`);
      return parsed;
    } finally {
      clearTimeout(timer);
    }
  }
}

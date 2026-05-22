export class MetaSwapClient {
  constructor({ baseUrl, apiKey }) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
  }

  health() {
    return this.get("/health");
  }

  plans() {
    return this.get("/developer/plans");
  }

  revenueScalePlan() {
    return this.get("/revenue/scale-plan");
  }

  rpc({ chain, method, params = [] }) {
    return this.post("/rpc/proxy", { chain, method, params });
  }

  accelerationQuote({ chain, urgency = "standard", estimatedGas = 21000 }) {
    return this.post("/tx/acceleration/quote", { chain, urgency, estimatedGas });
  }

  relayTransaction({ chain, rawTransaction, urgency = "standard" }) {
    return this.post("/tx/relay", { chain, rawTransaction, urgency, userConsent: true });
  }

  subscribeWebhook({ url, events }) {
    return this.post("/webhooks", { url, events });
  }

  async get(path) {
    return this.request("GET", path);
  }

  async post(path, body) {
    return this.request("POST", path, body);
  }

  async request(method, path, body) {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: {
        "content-type": "application/json",
        "x-api-key": this.apiKey
      },
      body: body ? JSON.stringify(body) : undefined
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error ?? `HTTP ${response.status}`);
    return payload;
  }
}

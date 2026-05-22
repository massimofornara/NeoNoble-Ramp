import { randomUUID } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import https from "node:https";

export class WiseClient {
  constructor({
    baseUrl,
    accessToken,
    profileId,
    balanceId,
    clientCertPath,
    clientKeyPath,
    caCertPath,
    timeoutMs = 15000
  }) {
    this.baseUrl = baseUrl;
    this.accessToken = accessToken;
    this.profileId = profileId;
    this.balanceId = balanceId;
    this.clientCertPath = clientCertPath;
    this.clientKeyPath = clientKeyPath;
    this.caCertPath = caCertPath;
    this.timeoutMs = timeoutMs;
  }

  configured() {
    const mtls = this.requiresMtls();
    return Boolean(
      this.baseUrl &&
      this.accessToken &&
      this.profileId &&
      (!mtls || (
        this.clientCertPath &&
        this.clientKeyPath &&
        existsSync(this.clientCertPath) &&
        existsSync(this.clientKeyPath)
      ))
    );
  }

  requiresMtls() {
    return Boolean(this.baseUrl?.includes("api-mtls"));
  }

  status() {
    return {
      provider: "wise",
      configured: this.configured(),
      baseUrl: this.baseUrl,
      mtlsRequired: this.requiresMtls(),
      profileId: Boolean(this.profileId),
      balanceId: Boolean(this.balanceId),
      clientCertificate: Boolean(this.clientCertPath && existsSync(this.clientCertPath)),
      clientPrivateKey: Boolean(this.clientKeyPath && existsSync(this.clientKeyPath)),
      caCertificate: Boolean(this.caCertPath && existsSync(this.caCertPath))
    };
  }

  async submitSepaPayout(instruction) {
    if (!this.configured()) {
      throw new Error("Wise production mTLS credentials are not configured");
    }
    const destination = instruction.destination ?? {};
    if (!destination.iban || !destination.name) {
      throw new Error("Wise SEPA payout requires destination.iban and destination.name");
    }
    if (this.balanceId) {
      const available = await this.availableBalance(instruction.asset ?? "EUR");
      if (available < Number(instruction.amount)) {
        throw new Error(`Wise ${instruction.asset ?? "EUR"} balance insufficient: available ${available}, required ${Number(instruction.amount)}`);
      }
    }
    const quote = await this.createQuote({
      sourceCurrency: instruction.asset ?? "EUR",
      targetCurrency: "EUR",
      sourceAmount: Number(instruction.amount)
    });
    const recipient = await this.createRecipient({
      currency: "EUR",
      name: destination.name,
      iban: destination.iban
    });
    const transfer = await this.createTransfer({
      targetAccount: recipient.id,
      quoteUuid: quote.id ?? quote.quoteUuid,
      reference: instruction.reference,
      customerTransactionId: instruction.idempotencyKey ?? instruction.reference ?? randomUUID()
    });
    const payment = await this.fundTransfer({
      transferId: transfer.id,
      type: this.balanceId ? "BALANCE" : "BANK_TRANSFER",
      balanceId: this.balanceId
    });
    return {
      provider: "wise",
      status: payment.status ?? transfer.status ?? "submitted",
      reference: instruction.reference,
      quote,
      recipient,
      transfer,
      payment
    };
  }

  async availableBalance(currency = "EUR") {
    const balances = await this.request("GET", `/v4/profiles/${this.profileId}/balances?types=STANDARD`);
    const selected = balances.find((balance) => {
      const idMatches = this.balanceId && String(balance.id) === String(this.balanceId);
      return idMatches || balance.currency === currency;
    });
    if (!selected) return 0;
    return Number(selected.amount?.value ?? selected.availableAmount?.value ?? 0);
  }

  async createQuote({ sourceCurrency, targetCurrency, sourceAmount }) {
    return await this.request("POST", `/v3/profiles/${this.profileId}/quotes`, {
      sourceCurrency,
      targetCurrency,
      sourceAmount,
      payOut: "BANK_TRANSFER",
      preferredPayIn: this.balanceId ? "BALANCE" : "BANK_TRANSFER"
    });
  }

  async createRecipient({ currency, name, iban }) {
    return await this.request("POST", "/v1/accounts", {
      profile: Number(this.profileId),
      accountHolderName: name,
      currency,
      type: "iban",
      details: {
        legalType: "PRIVATE",
        IBAN: iban
      }
    });
  }

  async createTransfer({ targetAccount, quoteUuid, reference, customerTransactionId }) {
    return await this.request("POST", `/v1/profiles/${this.profileId}/transfers`, {
      targetAccount,
      quoteUuid,
      customerTransactionId,
      details: {
        reference: reference ?? customerTransactionId
      }
    });
  }

  async fundTransfer({ transferId, type, balanceId }) {
    return await this.request("POST", `/v3/profiles/${this.profileId}/transfers/${transferId}/payments`, {
      type,
      balanceId
    });
  }

  request(method, path, body) {
    const url = new URL(path, this.baseUrl);
    const payload = body ? JSON.stringify(body) : "";
    const agent = this.clientCertPath && this.clientKeyPath && existsSync(this.clientCertPath) && existsSync(this.clientKeyPath)
      ? new https.Agent({
          cert: readFileSync(this.clientCertPath),
          key: readFileSync(this.clientKeyPath),
          ca: this.caCertPath && existsSync(this.caCertPath) ? readFileSync(this.caCertPath) : undefined,
          keepAlive: true
        })
      : new https.Agent({ keepAlive: true });
    return new Promise((resolve, reject) => {
      const req = https.request(url, {
        method,
        agent,
        timeout: this.timeoutMs,
        headers: {
          "authorization": `Bearer ${this.accessToken}`,
          "content-type": "application/json",
          "content-length": Buffer.byteLength(payload)
        }
      }, (res) => {
        let data = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => { data += chunk; });
        res.on("end", () => {
          const parsed = data ? JSON.parse(data) : {};
          if (res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`wise ${res.statusCode}: ${data}`));
            return;
          }
          resolve(parsed);
        });
      });
      req.on("timeout", () => req.destroy(new Error("wise request timed out")));
      req.on("error", reject);
      if (payload) req.write(payload);
      req.end();
    });
  }
}

import { SignedHttpClient } from "./signed-http-client.js";
import { WiseClient } from "./wise-client.js";

export class BankingAdapter {
  constructor(config) {
    this.wise = new WiseClient(config.wise ?? {});
    this.client = new SignedHttpClient({ name: "banking", ...config });
  }

  submitSepaPayout(instruction) {
    if (this.wise.configured()) return this.wise.submitSepaPayout(instruction);
    return this.client.request("POST", "/v1/payments/sepa-credit-transfer", instruction);
  }

  submitSwiftPayout(instruction) {
    return this.client.request("POST", "/v1/payments/swift", instruction);
  }

  issueVirtualIban(profile) {
    return this.client.request("POST", "/v1/accounts/virtual-iban", profile);
  }

  status() {
    return {
      wise: this.wise.status(),
      terminalConfigured: this.client.configured()
    };
  }
}

export class CardAdapter {
  constructor(config) {
    this.client = new SignedHttpClient({ name: "card", ...config });
  }

  submitPayout(instruction) {
    return this.client.request("POST", "/v1/card-payouts", instruction);
  }

  acquirePayment(instruction) {
    return this.client.request("POST", "/v1/acquiring/charges", instruction);
  }
}

export class MpcCustodyAdapter {
  constructor(config) {
    this.client = new SignedHttpClient({ name: "custody", ...config });
  }

  createWallet(request) {
    return this.client.request("POST", "/v1/wallets", request);
  }

  signTransaction(request) {
    return this.client.request("POST", "/v1/transactions/sign", request);
  }

  broadcastTransaction(request) {
    return this.client.request("POST", "/v1/transactions/broadcast", request);
  }
}

export class MarketMakerAdapter {
  constructor(config) {
    this.client = new SignedHttpClient({ name: "market-maker", ...config });
  }

  requestQuote(request) {
    return this.client.request("POST", "/v1/rfq", request);
  }
}

export class HedgingAdapter {
  constructor(config) {
    this.client = new SignedHttpClient({ name: "hedging", ...config });
  }

  submitHedgeOrder(order) {
    return this.client.request("POST", "/v1/orders", order);
  }
}

export class AmlAdapter {
  constructor(config) {
    this.client = new SignedHttpClient({ name: "aml", ...config });
  }

  screenTransaction(request) {
    return this.client.request("POST", "/v1/transactions/screen", request);
  }
}

export class TravelRuleAdapter {
  constructor(config) {
    this.client = new SignedHttpClient({ name: "travel-rule", ...config });
  }

  submitTransfer(request) {
    return this.client.request("POST", "/v1/transfers", request);
  }
}

export class BlockchainRpcAdapter {
  constructor({ rpcUrl, rpcUrls = [], chainId, deployerAddress, tokenFactoryAddress, namespace = "evm", retryCount = 3 }) {
    this.rpcUrls = rpcUrls.length ? rpcUrls : (rpcUrl ? [rpcUrl] : []);
    this.rpcUrl = this.rpcUrls[0];
    this.chainId = chainId;
    this.deployerAddress = deployerAddress;
    this.tokenFactoryAddress = tokenFactoryAddress;
    this.namespace = namespace;
    this.retryCount = retryCount;
    this.cursor = 0;
    this.health = new Map(this.rpcUrls.map((url) => [url, { failures: 0, lastOkAt: null, lastError: null }]));
  }

  configured() {
    return Boolean(this.rpcUrls.length && this.chainId);
  }

  async call(method, params = []) {
    if (!this.configured()) throw new Error(`Blockchain RPC for chain ${this.chainId ?? "unknown"} is not configured`);
    let lastError;
    for (let attempt = 0; attempt < Math.max(this.retryCount, this.rpcUrls.length); attempt++) {
      const url = this.nextUrl();
      try {
        const response = await fetch(url, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ jsonrpc: "2.0", id: Date.now(), method, params })
        });
        const payload = await response.json();
        if (payload.error) throw new Error(payload.error.message);
        this.health.set(url, { failures: 0, lastOkAt: new Date().toISOString(), lastError: null });
        return payload.result;
      } catch (error) {
        lastError = error;
        const current = this.health.get(url) ?? { failures: 0 };
        this.health.set(url, { ...current, failures: current.failures + 1, lastError: error.message });
      }
    }
    throw lastError;
  }

  nextUrl() {
    const url = this.rpcUrls[this.cursor % this.rpcUrls.length];
    this.cursor += 1;
    return url;
  }

  status() {
    return { chainId: this.chainId, namespace: this.namespace, providers: [...this.health.entries()].map(([url, health]) => ({ url, ...health })) };
  }

  blockNumber() {
    return this.namespace === "solana" ? this.call("getSlot") : this.call("eth_blockNumber");
  }

  nativeBalance(address) {
    return this.namespace === "solana"
      ? this.call("getBalance", [address])
      : this.call("eth_getBalance", [address, "latest"]);
  }

  tokenBalance({ tokenAddress, ownerAddress }) {
    if (this.namespace === "solana") {
      return this.call("getTokenAccountsByOwner", [
        ownerAddress,
        { mint: tokenAddress },
        { encoding: "jsonParsed" }
      ]);
    }
    const owner = ownerAddress.toLowerCase().replace("0x", "").padStart(64, "0");
    const data = `0x70a08231${owner}`;
    return this.call("eth_call", [{ to: tokenAddress, data }, "latest"]);
  }

  estimateGas(transaction) {
    return this.namespace === "solana"
      ? this.call("getLatestBlockhash")
      : this.call("eth_estimateGas", [transaction]);
  }

  broadcast(rawTransaction) {
    return this.namespace === "solana"
      ? this.call("sendTransaction", [rawTransaction])
      : this.call("eth_sendRawTransaction", [rawTransaction]);
  }
}

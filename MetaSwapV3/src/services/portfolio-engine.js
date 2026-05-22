const CHAIN_NATIVE = {
  ethereum: { symbol: "ETH", decimals: 18 },
  bnb: { symbol: "BNB", decimals: 18 },
  polygon: { symbol: "MATIC", decimals: 18 },
  base: { symbol: "ETH", decimals: 18 },
  solana: { symbol: "SOL", decimals: 9 }
};

export class PortfolioEngine {
  constructor({ walletService, assetRegistry, blockchainAdapters, pricingEngine, eventBus }) {
    this.walletService = walletService;
    this.assetRegistry = assetRegistry;
    this.blockchainAdapters = blockchainAdapters;
    this.pricingEngine = pricingEngine;
    this.eventBus = eventBus;
  }

  async portfolio(userId) {
    const sessions = [...new Map(
      this.walletService.sessionsForUser(userId).map((session) => [
        `${session.chain}:${session.address.toLowerCase()}`,
        session
      ])
    ).values()];
    const balances = [];
    for (const session of sessions) {
      balances.push(...await this.balancesForSession(session));
    }
    const totalUsd = balances.reduce((sum, row) => sum + row.valueUsd, 0);
    const result = { userId, generatedAt: new Date().toISOString(), totalUsd, balances };
    this.eventBus.publish("WalletPortfolioRefreshed", { userId, totalUsd, positions: balances.length });
    return result;
  }

  async balancesForSession(session) {
    const adapter = this.blockchainAdapters[session.chain];
    if (!adapter?.configured()) throw new Error(`RPC is required for ${session.chain}`);
    const native = await this.nativeBalance(adapter, session);
    const tokenBalances = [];
    for (const asset of this.assetRegistry.list()) {
      const tokenAddress = asset.contracts?.[session.chain];
      if (!tokenAddress) continue;
      try {
        tokenBalances.push(await this.tokenBalance(adapter, session, asset, tokenAddress));
      } catch (error) {
        this.eventBus.publish("WalletTokenBalanceUnavailable", {
          chain: session.chain,
          symbol: asset.symbol,
          tokenAddress,
          address: session.address,
          error: error.message
        });
        tokenBalances.push(this.position({
          chain: session.chain,
          symbol: asset.symbol,
          tokenAddress,
          address: session.address,
          amount: 0,
          status: "balance_unavailable"
        }));
      }
    }
    return [native, ...tokenBalances];
  }

  async nativeBalance(adapter, session) {
    const native = CHAIN_NATIVE[session.chain];
    const raw = await adapter.nativeBalance(session.address);
    const value = session.chain === "solana" ? Number(raw.value) : Number(BigInt(raw)) / 10 ** native.decimals;
    return this.position({ chain: session.chain, symbol: native.symbol, address: session.address, amount: value });
  }

  async tokenBalance(adapter, session, asset, tokenAddress) {
    const raw = await adapter.tokenBalance({ tokenAddress, ownerAddress: session.address });
    const amount = adapter.namespace === "solana"
      ? solanaTokenAmount(raw)
      : Number(raw && raw !== "0x" ? BigInt(raw) : 0n) / 10 ** (asset.decimals ?? 18);
    return this.position({ chain: session.chain, symbol: asset.symbol, tokenAddress, address: session.address, amount });
  }

  position({ chain, symbol, tokenAddress, address, amount, status = "ok" }) {
    const valueUsd = amount * this.pricingEngine.usdValue(symbol);
    return { chain, symbol, tokenAddress, address, amount, valueUsd, status };
  }
}

function solanaTokenAmount(raw) {
  const accounts = raw.value ?? [];
  return accounts.reduce((sum, account) => {
    const amount = account.account?.data?.parsed?.info?.tokenAmount?.uiAmount ?? 0;
    return sum + Number(amount);
  }, 0);
}

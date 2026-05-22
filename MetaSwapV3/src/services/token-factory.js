import { randomUUID } from "node:crypto";

export class TokenFactory {
  constructor({ assetRegistry, ledger, pricingEngine, eventBus, blockchainAdapters = {} }) {
    this.assetRegistry = assetRegistry;
    this.ledger = ledger;
    this.pricingEngine = pricingEngine;
    this.eventBus = eventBus;
    this.blockchainAdapters = blockchainAdapters;
  }

  async createToken({ issuerId, symbol, name, maxSupply, issuePriceUsd, chains = ["ethereum"], micaClassification = "utility", riskTier = "medium", contracts, decimals = 18 }) {
    if (!issuerId || !symbol || !maxSupply || !issuePriceUsd) throw new Error("Missing token fields");
    const normalizedSymbol = symbol.toUpperCase();
    const resolvedContracts = contracts ?? await this.resolveContracts(chains, normalizedSymbol);
    const asset = this.assetRegistry.register({
      assetId: randomUUID(),
      symbol: normalizedSymbol,
      name: name ?? normalizedSymbol,
      type: "token",
      standard: chains.includes("solana") && chains.length === 1 ? "SPL" : chains.length > 1 ? "MULTICHAIN_WRAPPED" : "ERC20",
      chains,
      contracts: resolvedContracts,
      issuerId,
      maxSupply,
      decimals,
      mintPolicy: "controlled",
      burnPolicy: "issuer",
      transferPolicy: "geo_restricted",
      micaClassification,
      riskTier,
      requiredTier: "basic",
      allowedJurisdictions: ["EU", "UK", "ROW"],
      lifecycle: "rfq",
      pricing: { issuePriceUsd, navUsd: issuePriceUsd }
    });
    this.pricingEngine.setOracle(normalizedSymbol, undefined);

    const external = this.ledger.ensureAccount("external", "mint", normalizedSymbol);
    this.ledger.credit(external, "available", maxSupply);
    const platformInventory = this.ledger.ensureAccount("platform", "inventory", normalizedSymbol);
    const issuerAccount = this.ledger.ensureAccount("issuer", issuerId, normalizedSymbol);
    const listingFloat = maxSupply * 0.02;
    this.ledger.postTransfer({ from: external, to: platformInventory, asset: normalizedSymbol, amount: listingFloat, memo: "controlled listing float" });
    this.ledger.postTransfer({ from: external, to: issuerAccount, asset: normalizedSymbol, amount: maxSupply - listingFloat, memo: "issuer treasury mint" });

    this.eventBus.publish("TokenCreated", { symbol: normalizedSymbol, issuerId, lifecycle: asset.lifecycle, contracts: resolvedContracts });
    return asset;
  }

  async resolveContracts(chains, symbol) {
    const contracts = {};
    for (const chain of chains) {
      const adapter = this.blockchainAdapters[chain];
      if (!adapter?.configured?.()) {
        throw new Error(`Contract address or configured blockchain RPC is required for ${chain}:${symbol}`);
      }
      const latestBlock = await adapter.blockNumber();
      contracts[chain] = `chain:${chain}:factory:${adapter.tokenFactoryAddress}:block:${latestBlock}`;
    }
    return contracts;
  }

  promoteLifecycle(symbol, lifecycle) {
    const asset = this.assetRegistry.get(symbol);
    asset.lifecycle = lifecycle;
    this.eventBus.publish("TokenLifecycleChanged", { symbol, lifecycle });
    return asset;
  }
}

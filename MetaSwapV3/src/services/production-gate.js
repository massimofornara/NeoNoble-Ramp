import { missingProductionKeys } from "../production-requirements.js";

export class ProductionGate {
  constructor({ config, blockchainAdapters }) {
    this.config = config;
    this.blockchainAdapters = blockchainAdapters;
  }

  validate() {
    if (this.config.environment !== "production") return { status: "not_required" };
    const missing = missingProductionKeys();
    for (const [chain, adapter] of Object.entries(this.blockchainAdapters)) {
      if (!adapter.configured()) missing.push(`${chain}.RPC_URLS/CHAIN_ID`);
      if (!adapter.tokenFactoryAddress) missing.push(`${chain}.TOKEN_FACTORY_ADDRESS`);
    }
    if (missing.length) throw new Error(`Production configuration incomplete: ${missing.join(", ")}`);
    return { status: "ready" };
  }
}

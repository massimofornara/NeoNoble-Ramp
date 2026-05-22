export class ProviderRegistry {
  constructor({ eventBus }) {
    this.eventBus = eventBus;
    this.providers = new Map();
  }

  register({ id, kind, priority = 100, status = "active", capabilities = [], metadata = {} }) {
    const provider = { id, kind, priority, status, capabilities, metadata, updatedAt: new Date().toISOString() };
    this.providers.set(id, provider);
    this.eventBus.publish("ProviderRegistered", provider);
    return provider;
  }

  setStatus({ id, status, reason }) {
    const provider = this.providers.get(id);
    if (!provider) throw new Error("Provider not found");
    provider.status = status;
    provider.reason = reason;
    provider.updatedAt = new Date().toISOString();
    this.eventBus.publish("ProviderStatusChanged", provider);
    return provider;
  }

  select({ kind, capability }) {
    const candidates = [...this.providers.values()]
      .filter((provider) => provider.kind === kind)
      .filter((provider) => provider.status === "active")
      .filter((provider) => !capability || provider.capabilities.includes(capability))
      .sort((a, b) => a.priority - b.priority);
    if (!candidates.length) throw new Error(`No active provider for ${kind}:${capability ?? "any"}`);
    return candidates[0];
  }

  list() {
    return [...this.providers.values()];
  }
}

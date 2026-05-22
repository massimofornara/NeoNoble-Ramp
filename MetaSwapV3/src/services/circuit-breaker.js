export class CircuitBreaker {
  constructor(eventBus) {
    this.eventBus = eventBus;
    this.marketStates = new Map();
  }

  state(market) {
    return this.marketStates.get(market) ?? { status: "open", reason: null };
  }

  assertOpen(market) {
    const state = this.state(market);
    if (state.status !== "open") throw new Error(`Market ${market} is ${state.status}: ${state.reason}`);
  }

  halt(market, reason) {
    const state = { status: "halted", reason, updatedAt: new Date().toISOString() };
    this.marketStates.set(market, state);
    this.eventBus.publish("CircuitBreakerHalted", { market, ...state });
    return state;
  }

  resume(market, reason = "operator_resume") {
    const state = { status: "open", reason, updatedAt: new Date().toISOString() };
    this.marketStates.set(market, state);
    this.eventBus.publish("CircuitBreakerResumed", { market, ...state });
    return state;
  }
}

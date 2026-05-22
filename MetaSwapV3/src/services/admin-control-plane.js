export class AdminControlPlane {
  constructor({ circuitBreaker, treasuryService, reconciliationEngine, eventBus }) {
    this.circuitBreaker = circuitBreaker;
    this.treasuryService = treasuryService;
    this.reconciliationEngine = reconciliationEngine;
    this.eventBus = eventBus;
  }

  haltMarket({ market, reason }) {
    return this.circuitBreaker.halt(market, reason);
  }

  resumeMarket({ market, reason }) {
    return this.circuitBreaker.resume(market, reason);
  }

  stressTest({ symbol, shockPercent }) {
    return this.treasuryService.stressTest(symbol, shockPercent);
  }

  reconcile() {
    return this.reconciliationEngine.run();
  }
}

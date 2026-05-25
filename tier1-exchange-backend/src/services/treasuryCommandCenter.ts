import type { TreasuryEngine } from "./treasuryEngine.js";

export class TreasuryCommandCenter {
  constructor(private readonly treasury: TreasuryEngine) {}

  status(): Record<string, unknown> {
    const report = this.treasury.report();
    return {
      ...report,
      commandMode: "segregated-hot-warm-cold",
      autoRebalanceEligible: report.rebalancing.some((item) => item.action === "rebalance_required"),
    };
  }
}

import { CrossingMatcher, type CrossingMatch } from "./crossingMatcher.js";
import { DarkNettingPool, type NettableIntent } from "./darkNettingPool.js";
import { InternalSettlementBook } from "./internalSettlementBook.js";

export interface CrossingDecision {
  priority: "internal-first";
  matches: CrossingMatch[];
  residualAmount: string;
  gasReductionEstimated: boolean;
  requiresExternalSettlement: boolean;
}

export class InternalCrossingEngine {
  constructor(
    private readonly pool = new DarkNettingPool(),
    private readonly matcher = new CrossingMatcher(),
    private readonly settlementBook = new InternalSettlementBook(),
  ) {}

  evaluate(intent: NettableIntent): CrossingDecision {
    const matches = this.matcher.match(intent, this.pool.compatible(intent));
    const residualAmount = matches.at(-1)?.residualAmount ?? intent.amount;
    if (matches.length > 0) {
      this.settlementBook.reserve(
        matches.flatMap((match) => [
          { intentId: intent.intentId, accountId: intent.accountId, asset: intent.fromAsset, amount: match.internalFillAmount, side: "debit" as const },
          { intentId: intent.intentId, accountId: intent.accountId, asset: intent.toAsset, amount: match.internalFillAmount, side: "credit" as const },
        ]),
      );
    }
    this.pool.add(intent);
    return {
      priority: "internal-first",
      matches,
      residualAmount,
      gasReductionEstimated: matches.length > 0,
      requiresExternalSettlement: Number(residualAmount) > 0,
    };
  }
}

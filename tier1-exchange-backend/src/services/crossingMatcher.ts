import type { NettableIntent } from "./darkNettingPool.js";

export interface CrossingMatch {
  matchedIntentId: string;
  internalFillAmount: string;
  residualAmount: string;
}

export class CrossingMatcher {
  match(intent: NettableIntent, candidates: NettableIntent[]): CrossingMatch[] {
    let remaining = Number(intent.amount);
    const matches: CrossingMatch[] = [];
    for (const candidate of candidates) {
      if (remaining <= 0) break;
      const fill = Math.min(remaining, Number(candidate.expectedAmount || candidate.amount));
      if (fill <= 0) continue;
      remaining -= fill;
      matches.push({
        matchedIntentId: candidate.intentId,
        internalFillAmount: String(fill),
        residualAmount: String(Math.max(0, remaining)),
      });
    }
    return matches;
  }
}

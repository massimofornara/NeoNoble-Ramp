import type { ExecutableRfqQuote, ScoredRfqQuote } from "./institutionalRfqTypes.js";

export class RFQScoreEngine {
  score(quotes: ExecutableRfqQuote[]): ScoredRfqQuote[] {
    return quotes
      .map((quote) => {
        const outputScore = Number(quote.amountOut);
        const gasPenalty = Number(quote.gasCostUsd || 0);
        const slippagePenalty = quote.slippageBps / 10_000;
        const failurePenalty = quote.failureProbability * outputScore;
        const expiryMs = Date.parse(quote.expiry) - Date.now();
        const expiryPenalty = expiryMs < Number(process.env.RFQ_MIN_EXPIRY_MS ?? 5_000) ? outputScore * 0.25 : 0;
        const guaranteeBonus = quote.makerFillGuarantee ? outputScore * 0.05 : 0;
        const privateSettlementBonus = quote.privateSettlementChannel ? outputScore * 0.02 : 0;
        return {
          quote,
          score: outputScore - gasPenalty - slippagePenalty - failurePenalty - expiryPenalty + guaranteeBonus + privateSettlementBonus,
          components: {
            outputScore,
            gasPenalty,
            slippagePenalty,
            failurePenalty,
            expiryPenalty,
            guaranteeBonus,
            privateSettlementBonus,
          },
        };
      })
      .sort((left, right) => right.score - left.score);
  }
}

import type { VenueQuote } from "./venueAdapter.js";

export interface ScoredRoute {
  quote: VenueQuote;
  score: number;
  scoreBreakdown: {
    outputValue: number;
    gasPenalty: number;
    slippagePenalty: number;
    failurePenalty: number;
    privateSettlementBonus: number;
    liquidityDepthScore: number;
    successProbabilityScore: number;
    historicalFillScore: number;
    sizePolicyScore: number;
  };
}

export class RouteScorer {
  score(quotes: VenueQuote[]): ScoredRoute[] {
    return quotes
      .filter((quote) => Date.parse(quote.expiresAt) > Date.now())
      .map((quote) => {
        const outputValue = Number(quote.outputAmount);
        const gasPenalty = Number(quote.gasCostUsd || 0);
        const slippagePenalty = outputValue * (quote.slippageBps / 10_000);
        const failurePenalty = outputValue * quote.failureProbability;
        const privateSettlementBonus = quote.privateSettlement ? outputValue * 0.0005 : 0;
        const executableBonus = quote.metadata.executable ? outputValue * 0.005 : 0;
        const makerGuaranteeBonus = quote.metadata.makerFillGuarantee ? outputValue * 0.0025 : 0;
        const rfqEmbeddedBonus = quote.liquiditySource === "0x_RFQ" ? outputValue * 0.004 : 0;
        const intentSolverBonus = quote.liquiditySource === "1inch_fusion" ? outputValue * 0.003 : 0;
        const liquidityDepthScore = outputValue * Math.min(0.01, Math.max(0, Number(quote.liquidityDepth || 0) / Math.max(1, outputValue)) * 0.0025);
        const executionSuccessProbability = Number(quote.metadata.executionSuccessProbability ?? 1 - quote.failureProbability);
        const successProbabilityScore = outputValue * Math.max(0, Math.min(1, executionSuccessProbability)) * 0.01;
        const historicalFillScore = outputValue * historicalFillSuccess(quote) * 0.006;
        const sizePolicyScore = outputValue * sizePolicyWeight(quote);
        return {
          quote,
          score:
            outputValue -
            gasPenalty -
            slippagePenalty -
            failurePenalty +
            privateSettlementBonus +
            executableBonus +
            makerGuaranteeBonus +
            rfqEmbeddedBonus +
            intentSolverBonus +
            liquidityDepthScore +
            successProbabilityScore +
            historicalFillScore +
            sizePolicyScore,
          scoreBreakdown: {
            outputValue,
            gasPenalty,
            slippagePenalty,
            failurePenalty,
            privateSettlementBonus: privateSettlementBonus + executableBonus + makerGuaranteeBonus + rfqEmbeddedBonus + intentSolverBonus,
            liquidityDepthScore,
            successProbabilityScore,
            historicalFillScore,
            sizePolicyScore,
          },
        };
      })
      .sort((left, right) => right.score - left.score);
  }
}

function historicalFillSuccess(quote: VenueQuote): number {
  const sourceKey = quote.liquiditySource.toUpperCase().replace(/[^A-Z0-9]+/g, "_");
  const venueKey = quote.venue.toUpperCase().replace(/[^A-Z0-9]+/g, "_");
  const configured = Number(
    quote.metadata.historicalFillSuccessRate ??
      process.env[`VENUE_${sourceKey}_HISTORICAL_FILL_SUCCESS`] ??
      process.env[`VENUE_${venueKey}_HISTORICAL_FILL_SUCCESS`] ??
      defaultHistoricalSuccess(quote),
  );
  return Number.isFinite(configured) ? Math.max(0, Math.min(1, configured)) : 0.82;
}

function defaultHistoricalSuccess(quote: VenueQuote): number {
  if (quote.liquiditySource === "0x_RFQ") return 0.9;
  if (quote.liquiditySource === "1inch_fusion") return 0.88;
  if (quote.metadata.executable) return 0.84;
  if (quote.venue === "pancakeswap" || quote.venue === "uniswap") return 0.78;
  return 0.75;
}

function sizePolicyWeight(quote: VenueQuote): number {
  const amount = Number(quote.inputAmount);
  const source = quote.liquiditySource.toLowerCase();
  if (!Number.isFinite(amount)) return 0;
  if (amount > 1_000 && (source.includes("rfq") || source.includes("fusion") || quote.privateSettlement)) return 0.012;
  if (amount > 1_000 && (source.includes("pancake") || source.includes("uniswap-v2"))) return -0.02;
  if (amount <= 1_000 && quote.metadata.executable) return 0.004;
  return 0;
}

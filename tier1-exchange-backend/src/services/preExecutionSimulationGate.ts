import { JsonRpcProvider } from "ethers";
import { metrics, logJson } from "../core/observability.js";
import type { QuoteRequest, VenueQuote } from "./venueAdapter.js";
import { asRecord, firstRecord, hasExecutableTransaction } from "./dexAdapterUtils.js";
import { normalizeFailureReason } from "./smartRetryPolicy.js";

export interface PreExecutionGateResult {
  valid: boolean;
  confidence: number;
  quoteFresh: boolean;
  ageMs: number;
  calldataValid: boolean;
  ethCallPassed: boolean;
  gasEstimatePassed: boolean;
  approvalDependency: boolean;
  normalizedFailureReason?: string;
  rejectionReason?: string;
  gasEstimate?: string;
}

export class PreExecutionSimulationGate {
  async validateQuotes(quotes: VenueQuote[], request: QuoteRequest): Promise<{ validQuotes: VenueQuote[]; rejected: Array<{ quote: VenueQuote; result: PreExecutionGateResult }> }> {
    const settled = await Promise.all(quotes.map(async (quote) => ({ quote, result: await this.evaluate(quote, request) })));
    const threshold = Number(process.env.PRE_EXECUTION_SUCCESS_THRESHOLD ?? 0.65);
    const validQuotes: VenueQuote[] = [];
    const rejected: Array<{ quote: VenueQuote; result: PreExecutionGateResult }> = [];
    for (const item of settled) {
      const annotated = {
        ...item.quote,
        failureProbability: Math.max(item.quote.failureProbability, Number((1 - item.result.confidence).toFixed(4))),
        metadata: {
          ...item.quote.metadata,
          preExecution: item.result,
          executionSuccessProbability: item.result.confidence,
        },
      };
      if (item.result.valid && item.result.confidence >= threshold) {
        validQuotes.push(annotated);
      } else {
        rejected.push({ quote: annotated, result: item.result });
      }
      metrics.inc("exchange_pre_execution_gate_total", {
        venue: item.quote.venue,
        source: item.quote.liquiditySource,
        valid: item.result.valid && item.result.confidence >= threshold,
        reason: item.result.normalizedFailureReason ?? "OK",
      });
    }
    return { validQuotes, rejected };
  }

  async evaluate(quote: VenueQuote, request: QuoteRequest): Promise<PreExecutionGateResult> {
    const ageMs = quoteAgeMs(quote);
    const quoteFresh = ageMs <= Number(process.env.EXECUTABLE_QUOTE_MAX_AGE_MS ?? 8_000);
    const raw = asRecord(quote.metadata.raw ?? quote.metadata);
    const transaction = firstRecord(raw.transaction, raw.tx, raw.settlementTransaction, asRecord(raw.execution).transaction, asRecord(raw.execution).tx);
    const approvalDependency = Boolean(raw.allowanceTarget || raw.approvalTarget || raw.spender || quote.metadata.allowanceTarget);
    if (!transaction) {
      const ammQuoteValid = quote.venue === "pancakeswap" || quote.venue === "uniswap";
      return {
        valid: ammQuoteValid && quoteFresh,
        confidence: ammQuoteValid && quoteFresh ? 0.68 : 0,
        quoteFresh,
        ageMs,
        calldataValid: ammQuoteValid,
        ethCallPassed: ammQuoteValid,
        gasEstimatePassed: ammQuoteValid,
        approvalDependency: false,
        normalizedFailureReason: ammQuoteValid ? undefined : "CALLDATA_INVALID",
        rejectionReason: ammQuoteValid ? undefined : "missing executable transaction calldata",
      };
    }
    const calldataValid = hasExecutableTransaction({ transaction });
    if (!calldataValid) {
      return this.rejected(quoteFresh, ageMs, approvalDependency, "CALLDATA_INVALID", "invalid executable transaction calldata");
    }
    const rpcUrl = process.env.BSC_RPC_URL;
    const treasuryAddress = process.env.TREASURY_ADDRESS;
    if (!rpcUrl || !treasuryAddress) {
      return this.rejected(quoteFresh, ageMs, approvalDependency, "RPC_TIMEOUT", "simulation RPC or treasury address not configured");
    }
    if (!quoteFresh) {
      return this.rejected(false, ageMs, approvalDependency, "RFQ_EXPIRED", "quote freshness exceeded pre-execution threshold");
    }
    try {
      const provider = new JsonRpcProvider(rpcUrl, request.chainId);
      const tx = {
        from: treasuryAddress,
        to: String(transaction.to ?? transaction.target),
        data: String(transaction.data ?? transaction.calldata ?? "0x"),
        value: BigInt(String(transaction.valueWei ?? transaction.value ?? "0")),
      };
      await provider.call(tx);
      const gasEstimate = await provider.estimateGas(tx);
      return {
        valid: true,
        confidence: confidenceFor(quote, true, true, false),
        quoteFresh,
        ageMs,
        calldataValid,
        ethCallPassed: true,
        gasEstimatePassed: true,
        approvalDependency,
        gasEstimate: gasEstimate.toString(),
      };
    } catch (error) {
      const reason = normalizeFailureReason(error);
      if (approvalDependency && reason === "GAS_REVERT") {
        logJson("pre-execution-gate", "approval_dependency_simulation_deferred", {
          venue: quote.venue,
          source: quote.liquiditySource,
          transactionId: request.intentId,
          reason,
        });
        return {
          valid: true,
          confidence: confidenceFor(quote, false, false, true),
          quoteFresh,
          ageMs,
          calldataValid,
          ethCallPassed: false,
          gasEstimatePassed: false,
          approvalDependency,
          normalizedFailureReason: reason,
          rejectionReason: "settlement simulation deferred until approval pre-transaction is confirmed",
        };
      }
      return this.rejected(quoteFresh, ageMs, approvalDependency, reason, error instanceof Error ? error.message : String(error));
    }
  }

  private rejected(
    quoteFresh: boolean,
    ageMs: number,
    approvalDependency: boolean,
    normalizedFailureReason: string,
    rejectionReason: string,
  ): PreExecutionGateResult {
    return {
      valid: false,
      confidence: 0,
      quoteFresh,
      ageMs,
      calldataValid: false,
      ethCallPassed: false,
      gasEstimatePassed: false,
      approvalDependency,
      normalizedFailureReason,
      rejectionReason,
    };
  }
}

function quoteAgeMs(quote: VenueQuote): number {
  const receivedAt = typeof quote.metadata.quoteReceivedAt === "string" ? Date.parse(quote.metadata.quoteReceivedAt) : Number.NaN;
  if (Number.isFinite(receivedAt)) return Math.max(0, Date.now() - receivedAt);
  const ttlMs = Number(process.env.QUOTE_TTL_MS ?? 20_000);
  const expiresAt = Date.parse(quote.expiresAt);
  return Number.isFinite(expiresAt) ? Math.max(0, ttlMs - Math.max(0, expiresAt - Date.now())) : ttlMs;
}

function confidenceFor(quote: VenueQuote, ethCallPassed: boolean, gasEstimatePassed: boolean, approvalDependency: boolean): number {
  const freshnessScore = 0.2;
  const calldataScore = 0.15;
  const simulationScore = ethCallPassed ? 0.25 : approvalDependency ? 0.14 : 0;
  const gasScore = gasEstimatePassed ? 0.15 : approvalDependency ? 0.08 : 0;
  const venueReliability = historicalFillSuccess(quote);
  const providerScore = Math.max(0, Math.min(0.15, venueReliability * 0.15));
  const failurePenalty = Math.max(0, Math.min(0.2, quote.failureProbability * 0.2));
  return Math.max(0, Math.min(0.99, freshnessScore + calldataScore + simulationScore + gasScore + providerScore - failurePenalty));
}

function historicalFillSuccess(quote: VenueQuote): number {
  const value = Number(quote.metadata.historicalFillSuccessRate ?? process.env[`VENUE_${envKey(quote.liquiditySource)}_HISTORICAL_FILL_SUCCESS`] ?? 0.82);
  return Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0.82;
}

function envKey(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9]+/g, "_");
}

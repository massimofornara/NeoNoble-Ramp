import type { ExecutionVenueAdapter, QuoteRequest, VenueQuote } from "./venueAdapter.js";
import {
  appendQuery,
  asRecord,
  assetAddress,
  buildDexQuote,
  fetchJson,
  firstRecord,
  hasExecutableTransaction,
  rawInputAmount,
  routableAsset,
  stringField,
} from "./dexAdapterUtils.js";

const ONEINCH_FUSION_QUOTE_URL = "https://api.1inch.com/fusion/quoter/v2.0/{chain}/quote/receive";
const ONEINCH_SWAP_BASE_URL = "https://api.1inch.dev/swap/v6.0";

export class OneInchFusionAdapter implements ExecutionVenueAdapter {
  readonly venue = "1inch" as const;

  async quote(request: QuoteRequest): Promise<VenueQuote | undefined> {
    const apiKey = process.env.ONEINCH_API_KEY;
    if (!apiKey) return undefined;
    const taker = process.env.TREASURY_ADDRESS;
    if (!taker || !/^0x[a-fA-F0-9]{40}$/.test(taker)) {
      throw new Error("1inch executable quote requires TREASURY_ADDRESS");
    }

    const headers = {
      Authorization: `Bearer ${apiKey}`,
      accept: "application/json",
    };
    const fusion = await this.fusionQuote(request, taker, headers).catch((error: unknown) => ({
      unavailableReason: error instanceof Error ? error.message : String(error),
    }));
    const executableFusion = this.quoteFromBody(request, "1inch_fusion", fusion, {
      privateSettlement: true,
      failureProbability: 0.015,
      extraMetadata: {
        intentSolver: "1inch-fusion",
        resolverCompetition: true,
        partialFillSupported: true,
        mevResistant: true,
      },
    });
    if (executableFusion?.metadata.executable) return executableFusion;

    const swap = await this.swapQuote(request, taker, headers, asRecord(fusion)).catch((error: unknown) => ({
      unavailableReason: error instanceof Error ? error.message : String(error),
    }));
    const executableSwap = this.quoteFromBody(request, "1inch_swap_v6", swap, {
      privateSettlement: false,
      failureProbability: 0.03,
      extraMetadata: {
        fusionQuote: asRecord(fusion),
        partialFillSupported: true,
        mevResistant: Boolean(executableFusion),
      },
    });
    const quote = executableSwap ?? executableFusion;
    if (quote) return quote;
    throw new Error(`1inch unavailable: fusion=${String(fusion.unavailableReason ?? "no executable quote")}; swap=${String(swap.unavailableReason ?? "no executable quote")}`);
  }

  private async fusionQuote(request: QuoteRequest, taker: string, headers: Record<string, string>): Promise<Record<string, unknown>> {
    const configured = process.env.ONEINCH_FUSION_QUOTE_URL ?? ONEINCH_FUSION_QUOTE_URL;
    const candidates = unique([configured, ONEINCH_FUSION_QUOTE_URL]);
    let lastError: unknown;
    for (const candidate of candidates) {
      const url = new URL(candidate.replace("{chain}", String(request.chainId)));
      appendQuery(url, {
        chainId: request.chainId,
        src: assetAddress(request.fromAsset, request.chainId),
        dst: assetAddress(request.toAsset, request.chainId),
        fromTokenAddress: assetAddress(request.fromAsset, request.chainId),
        toTokenAddress: assetAddress(request.toAsset, request.chainId),
        amount: rawInputAmount(request),
        walletAddress: taker,
        fromAddress: taker,
        enableEstimate: "true",
      });
      try {
        return await fetchJson(url, headers, "1inch Fusion quote");
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError instanceof Error ? lastError : new Error(String(lastError));
  }

  private async swapQuote(
    request: QuoteRequest,
    taker: string,
    headers: Record<string, string>,
    fusionQuote: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const base = (process.env.ONEINCH_SWAP_BASE_URL ?? ONEINCH_SWAP_BASE_URL).replace(/\/+$/, "");
    const url = new URL(`${base}/${request.chainId}/swap`);
    appendQuery(url, {
      src: assetAddress(request.fromAsset, request.chainId),
      dst: assetAddress(request.toAsset, request.chainId),
      amount: rawInputAmount(request),
      from: taker,
      slippage: ((request.slippageBps ?? Number(process.env.SWAP_SLIPPAGE_BPS ?? 75)) / 100).toFixed(2),
      disableEstimate: "false",
      allowPartialFill: "true",
    });
    const swap = await fetchJson(url, headers, "1inch swap");
    const approvalTarget = await this.approvalTarget(request.chainId, headers).catch(() => undefined);
    return {
      ...swap,
      fusionQuote,
      transaction: firstRecord(swap.tx, swap.transaction),
      allowanceTarget: approvalTarget,
    };
  }

  private async approvalTarget(chainId: number, headers: Record<string, string>): Promise<string | undefined> {
    const base = (process.env.ONEINCH_SWAP_BASE_URL ?? ONEINCH_SWAP_BASE_URL).replace(/\/+$/, "");
    const url = new URL(`${base}/${chainId}/approve/spender`);
    const response = await fetchJson(url, headers, "1inch approve spender");
    const spender = stringField(response, "address", "spender");
    return spender && /^0x[a-fA-F0-9]{40}$/.test(spender) ? spender : undefined;
  }

  private quoteFromBody(
    request: QuoteRequest,
    liquiditySource: string,
    body: Record<string, unknown>,
    options: {
      privateSettlement: boolean;
      failureProbability: number;
      extraMetadata: Record<string, unknown>;
    },
  ): VenueQuote | undefined {
    if (body.unavailableReason) return undefined;
    const transaction = firstRecord(body.transaction, body.tx, body.settlementTransaction, asRecord(body.execution).transaction, asRecord(body.execution).tx);
    const raw = {
      ...body,
      transaction,
      provider: "1inch",
    };
    const outputAmountRaw =
      stringField(body, "dstAmount", "toAmount", "buyAmount", "outputAmount", "receiveAmount") ??
      stringField(asRecord(body.quote), "dstAmount", "toAmount", "buyAmount", "outputAmount", "receiveAmount");
    return buildDexQuote({
      request,
      venue: this.venue,
      liquiditySource,
      quoteId: stringField(body, "quoteId", "orderHash", "auctionId"),
      route: [routableAsset(request.fromAsset, request.chainId), routableAsset(request.toAsset, request.chainId)],
      outputAmountRaw,
      gasCostUsd: "0",
      failureProbability: options.failureProbability,
      privateSettlement: options.privateSettlement,
      expiresAt: stringField(body, "expiry", "expiresAt", "deadline"),
      metadata: {
        ...options.extraMetadata,
        raw,
        executable: hasExecutableTransaction(raw),
        providerSlippageBps: request.slippageBps ?? Number(process.env.SWAP_SLIPPAGE_BPS ?? 75),
        source: liquiditySource,
        calldataExecutionMode: hasExecutableTransaction(raw),
        allowanceTarget: stringField(body, "allowanceTarget", "approvalTarget", "spender"),
      },
    });
  }
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

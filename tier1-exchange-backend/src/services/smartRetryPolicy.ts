export type FailureTaxonomy =
  | "RPC_TIMEOUT"
  | "NONCE_MISMATCH"
  | "TRANSIENT_REVERT"
  | "SLIPPAGE_EXCEEDED"
  | "RFQ_EXPIRED"
  | "INSUFFICIENT_LIQUIDITY"
  | "GAS_REVERT"
  | "CALLDATA_INVALID"
  | "SETTLEMENT_TIMEOUT"
  | "EXECUTION_FAILED";

export function normalizeFailureReason(error: unknown): FailureTaxonomy {
  const message = error instanceof Error ? error.message : String(error);
  if (/timeout|timed out|ETIMEDOUT|ECONNRESET|network error|fetch failed|server response 5\d\d/i.test(message)) return "RPC_TIMEOUT";
  if (/nonce too low|nonce has already been used|replacement transaction underpriced|already known|known transaction/i.test(message)) return "NONCE_MISMATCH";
  if (/transient|temporar|try again|header not found|missing trie node|rate limit/i.test(message)) return "TRANSIENT_REVERT";
  if (/slippage|amountOutMin|INSUFFICIENT_OUTPUT_AMOUNT|price impact/i.test(message)) return "SLIPPAGE_EXCEEDED";
  if (/expired|quote expired|deadline/i.test(message)) return "RFQ_EXPIRED";
  if (/insufficient liquidity|PATHFINDER_NOT_FOUND|NO_ROUTE|toTokenAmount.*0/i.test(message)) return "INSUFFICIENT_LIQUIDITY";
  if (/invalid calldata|calldata|bad target|invalid transaction/i.test(message)) return "CALLDATA_INVALID";
  if (/not reached|pending|confirmations|receipt/i.test(message)) return "SETTLEMENT_TIMEOUT";
  if (/revert|CALL_EXCEPTION|estimateGas|execution reverted|gas required exceeds allowance/i.test(message)) return "GAS_REVERT";
  return "EXECUTION_FAILED";
}

export function isRetryableBroadcastFailure(error: unknown): boolean {
  const reason = normalizeFailureReason(error);
  return reason === "RPC_TIMEOUT" || reason === "NONCE_MISMATCH" || reason === "TRANSIENT_REVERT";
}

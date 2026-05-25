import type { RpcReceipt } from "./rpcQuorum.js";

export class ReorgDetector {
  detect(receipts: RpcReceipt[]): { reorgDetected: boolean; blockNumbers: string[] } {
    const blockNumbers = receipts.map((receipt) => String(receipt.blockNumber ?? "")).filter(Boolean);
    return {
      reorgDetected: new Set(blockNumbers).size > 1,
      blockNumbers,
    };
  }
}

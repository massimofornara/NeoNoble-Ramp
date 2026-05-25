import { ReorgDetector } from "./reorgDetector.js";
import { RpcQuorum } from "./rpcQuorum.js";
import { TxEscalator } from "./txEscalator.js";
import { MempoolMonitor } from "./mempoolMonitor.js";

export interface WatchtowerFinality {
  valid: boolean;
  receiptStatus: "success" | "failed" | "pending";
  observedConfirmations: number;
  requiredConfirmations: number;
  blockNumber?: number;
  reorgDetected: boolean;
  shouldEscalate: boolean;
  quorum: {
    required: number;
    receipts: number;
    consensus: boolean;
  };
  mempool?: Record<string, unknown>;
  replacementRequired: boolean;
}

export class WatchtowerService {
  constructor(
    private readonly quorum = new RpcQuorum(),
    private readonly reorgDetector = new ReorgDetector(),
    private readonly escalator = new TxEscalator(),
  ) {}

  async verify(txHash: string, firstSeenAt: string, requiredConfirmations: number): Promise<WatchtowerFinality> {
    const { receipt, responses, quorum } = await this.quorum.receipt(txHash);
    const reorg = this.reorgDetector.detect(responses);
    if (responses.length < quorum || !receipt) {
      const mempool = await new MempoolMonitor(this.quorum).status(txHash);
      const shouldEscalate = this.escalator.shouldEscalate({ firstSeenAt, observedConfirmations: 0, receiptStatus: "pending" });
      return {
        valid: false,
        receiptStatus: "pending",
        observedConfirmations: 0,
        requiredConfirmations,
        reorgDetected: reorg.reorgDetected,
        shouldEscalate,
        quorum: {
          required: quorum,
          receipts: responses.length,
          consensus: responses.length >= quorum,
        },
        mempool,
        replacementRequired: shouldEscalate && !Boolean(mempool.mined),
      };
    }
    const latest = await this.quorum.blockNumber();
    const blockNumber = Number.parseInt(String(receipt.blockNumber ?? "0x0").slice(2), 16);
    const observedConfirmations = Math.max(0, latest - blockNumber + 1);
    const success = String(receipt.status).toLowerCase() === "0x1";
    return {
      valid: success && !reorg.reorgDetected && observedConfirmations >= requiredConfirmations,
      receiptStatus: success ? "success" : "failed",
      observedConfirmations,
      requiredConfirmations,
      blockNumber,
      reorgDetected: reorg.reorgDetected,
      shouldEscalate: this.escalator.shouldEscalate({
        firstSeenAt,
        observedConfirmations,
        receiptStatus: success ? "success" : "failed",
      }),
      quorum: {
        required: quorum,
        receipts: responses.length,
        consensus: responses.length >= quorum,
      },
      replacementRequired: reorg.reorgDetected || (success && observedConfirmations === 0 && this.escalator.shouldEscalate({
        firstSeenAt,
        observedConfirmations,
        receiptStatus: "success",
      })),
    };
  }
}

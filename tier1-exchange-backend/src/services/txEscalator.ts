export class TxEscalator {
  shouldEscalate(input: { firstSeenAt: string; observedConfirmations: number; receiptStatus: "success" | "failed" | "pending" }): boolean {
    if (input.receiptStatus === "failed") return false;
    if (input.observedConfirmations > 0) return false;
    return Date.now() - Date.parse(input.firstSeenAt) > Number(process.env.STUCK_TX_ESCALATION_MS ?? 120_000);
  }
}

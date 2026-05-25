export class WithdrawalGovernance {
  rules(amountUsd: string): Record<string, unknown> {
    const threshold = Number(process.env.WITHDRAWAL_GOVERNANCE_THRESHOLD_USD ?? 250_000);
    return {
      amountUsd,
      governanceRequired: Number(amountUsd) >= threshold,
      ruleSet: "institutional-withdrawal-governance",
    };
  }
}

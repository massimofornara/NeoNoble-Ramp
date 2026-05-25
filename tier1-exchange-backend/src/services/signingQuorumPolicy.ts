export class SigningQuorumPolicy {
  evaluate(amountUsd: string): Record<string, unknown> {
    const value = Number(amountUsd);
    const highValue = value >= Number(process.env.MPC_HIGH_VALUE_THRESHOLD_USD ?? 1_000_000);
    return {
      requiredSigners: highValue ? Number(process.env.MPC_HIGH_VALUE_SIGNERS ?? 3) : Number(process.env.MPC_DEFAULT_SIGNERS ?? 1),
      policy: highValue ? "high-value-mpc-quorum" : "standard-hot-wallet-quorum",
      amountUsd,
    };
  }
}

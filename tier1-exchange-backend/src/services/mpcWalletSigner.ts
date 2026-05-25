import { MultiSigTreasury } from "./multiSigTreasury.js";

export class MpcWalletSigner {
  constructor(private readonly multiSig = new MultiSigTreasury()) {}

  signingEnvelope(amountUsd: string): Record<string, unknown> {
    return {
      signingMode: process.env.MPC_SIGNER_URL ? "mpc-external-signer" : "treasury-signer-fallback",
      mpcConfigured: Boolean(process.env.MPC_SIGNER_URL),
      policy: this.multiSig.policy(amountUsd),
    };
  }
}

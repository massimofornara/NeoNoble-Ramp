import { SigningQuorumPolicy } from "./signingQuorumPolicy.js";
import { WalletSegregation } from "./walletSegregation.js";
import { WithdrawalGovernance } from "./withdrawalGovernance.js";

export class MultiSigTreasury {
  constructor(
    private readonly quorum = new SigningQuorumPolicy(),
    private readonly segregation = new WalletSegregation(),
    private readonly governance = new WithdrawalGovernance(),
  ) {}

  policy(amountUsd: string): Record<string, unknown> {
    return {
      walletSegregation: this.segregation.policy(),
      signingQuorum: this.quorum.evaluate(amountUsd),
      withdrawalGovernance: this.governance.rules(amountUsd),
    };
  }
}

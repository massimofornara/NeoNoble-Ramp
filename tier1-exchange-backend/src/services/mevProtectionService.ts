import { EncryptedOrderflow } from "./encryptedOrderflow.js";
import { PrivateRelayRouter } from "./privateRelayRouter.js";

export class MevProtectionService {
  constructor(
    private readonly relayRouter = new PrivateRelayRouter(),
    private readonly encryptedOrderflow = new EncryptedOrderflow(),
  ) {}

  protect(input: { chainId: number; metadata: Record<string, unknown> }): Record<string, unknown> {
    return {
      relay: this.relayRouter.select({ chainId: input.chainId }),
      orderflow: this.encryptedOrderflow.envelope(input.metadata),
      antiSandwich: true,
      frontrunProtection: true,
    };
  }
}

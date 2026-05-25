export class WalletService {
  async assertWalletReady(accountId: string): Promise<void> {
    if (!accountId || accountId.length < 3) {
      throw new Error("accountId is required and must identify a wallet account");
    }
  }
}

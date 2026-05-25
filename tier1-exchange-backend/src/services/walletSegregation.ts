export class WalletSegregation {
  policy(): Record<string, unknown> {
    return {
      hotWallet: process.env.TREASURY_ADDRESS ? "configured" : "missing",
      warmWallet: process.env.WARM_TREASURY_ADDRESS ? "configured" : "missing",
      coldWallet: process.env.COLD_TREASURY_ADDRESS ? "configured" : "missing",
      segregation: "hot-warm-cold",
    };
  }
}

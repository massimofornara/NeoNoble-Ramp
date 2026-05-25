export class ComplianceService {
  async assertAllowed(accountId: string): Promise<void> {
    if (accountId.toLowerCase().startsWith("blocked")) {
      throw new Error("Compliance/KYC rejected account");
    }
  }
}

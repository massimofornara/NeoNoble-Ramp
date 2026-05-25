export interface InternalSettlementLeg {
  intentId: string;
  accountId: string;
  asset: string;
  amount: string;
  side: "debit" | "credit";
}

export class InternalSettlementBook {
  private readonly legs: InternalSettlementLeg[] = [];

  reserve(legs: InternalSettlementLeg[]): void {
    this.legs.push(...legs);
  }

  all(): InternalSettlementLeg[] {
    return [...this.legs];
  }
}

export interface NettableIntent {
  intentId: string;
  accountId: string;
  fromAsset: string;
  toAsset: string;
  amount: string;
  expectedAmount: string;
}

export class DarkNettingPool {
  private readonly intents: NettableIntent[] = [];

  add(intent: NettableIntent): void {
    this.intents.push(intent);
  }

  compatible(intent: NettableIntent): NettableIntent[] {
    return this.intents.filter(
      (candidate) =>
        candidate.intentId !== intent.intentId &&
        candidate.fromAsset === intent.toAsset &&
        candidate.toAsset === intent.fromAsset &&
        Number(candidate.amount) > 0,
    );
  }
}

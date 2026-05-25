export interface ClearingItem {
  intentId: string;
  asset: string;
  amount: string;
  direction: "in" | "out";
}

export class ClearingQueue {
  private readonly items: ClearingItem[] = [];

  enqueue(item: ClearingItem): void {
    this.items.push(item);
  }

  pending(): ClearingItem[] {
    return [...this.items];
  }
}

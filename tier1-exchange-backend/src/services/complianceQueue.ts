export interface ComplianceQueueItem {
  intentId: string;
  accountId: string;
  riskScore: number;
  queuedAt: string;
  reason: string;
}

export class ComplianceQueue {
  private readonly items: ComplianceQueueItem[] = [];

  enqueue(item: Omit<ComplianceQueueItem, "queuedAt">): ComplianceQueueItem {
    const queued = { ...item, queuedAt: new Date().toISOString() };
    this.items.push(queued);
    return queued;
  }

  all(): ComplianceQueueItem[] {
    return [...this.items];
  }

  pending(): ComplianceQueueItem[] {
    return this.all();
  }
}

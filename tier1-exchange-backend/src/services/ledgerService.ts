import type { DomainEvent, EventBus, LedgerAppendInput, LedgerEntry } from "../core/types.js";
import { decimalToUnits, unitsToDecimal, type EventStore, type IdempotencyStore, type LedgerStore } from "../core/store.js";

export class LedgerService {
  constructor(
    private readonly bus: EventBus,
    private readonly events: EventStore,
    private readonly ledger: LedgerStore,
    private readonly idempotency: IdempotencyStore,
  ) {}

  registerConsumers(): void {
    this.bus.subscribe("settlement.confirmed", "ledger-service.settlement-confirmed", async (event) => {
      await this.append({
        idempotencyKey: `settlement:${event.eventId}:user-credit`,
        transactionId: event.transactionId,
        accountId: String(this.findAccountId(event.transactionId) ?? "unknown-account"),
        asset: String(this.findSettlementPayload(event.transactionId)?.asset ?? "UNKNOWN"),
        amount: String(this.findSettlementPayload(event.transactionId)?.amount ?? "0"),
        direction: "credit",
        reason: "settlement_confirmed_user_credit",
        metadata: {
          settlementId: event.payload.settlementId,
          providerReference: event.payload.providerReference,
          txHash: event.payload.txHash,
          adapter: event.payload.adapter,
          chainId: event.payload.chainId,
          settlementProofHash: event.payload.settlementProofHash,
          valuation: this.findSettlementPayload(event.transactionId)?.valuation ?? {},
        },
      });
      await this.append({
        idempotencyKey: `settlement:${event.eventId}:exchange-debit`,
        transactionId: event.transactionId,
        accountId: "exchange-clearing",
        asset: String(this.findSettlementPayload(event.transactionId)?.asset ?? "UNKNOWN"),
        amount: negateDecimal(String(this.findSettlementPayload(event.transactionId)?.amount ?? "0")),
        direction: "debit",
        reason: "settlement_confirmed_exchange_debit",
        metadata: {
          settlementId: event.payload.settlementId,
          providerReference: event.payload.providerReference,
          txHash: event.payload.txHash,
          adapter: event.payload.adapter,
          chainId: event.payload.chainId,
          settlementProofHash: event.payload.settlementProofHash,
          valuation: this.findSettlementPayload(event.transactionId)?.valuation ?? {},
        },
      });
    });
  }

  async append(input: LedgerAppendInput): Promise<LedgerEntry & { duplicate?: boolean }> {
    const existing = this.idempotency.get<LedgerEntry & { duplicate?: boolean }>("ledger.append", input.idempotencyKey);
    if (existing) return { ...existing, duplicate: true };

    const delta = input.direction === "debit" && !input.amount.startsWith("-") ? `-${input.amount}` : input.amount;
    const event = await this.bus.publish("ledger.append", input.transactionId, {
      accountId: input.accountId,
      asset: input.asset,
      amount: input.amount,
      delta,
      direction: input.direction,
      reason: input.reason,
      metadata: input.metadata ?? {},
    });

    const entry = await this.ledger.append({
      eventId: event.eventId,
      transactionId: input.transactionId,
      accountId: input.accountId,
      asset: input.asset,
      delta,
      amount: input.amount,
      direction: input.direction,
      reason: input.reason,
      metadata: input.metadata ?? {},
    });
    return this.idempotency.set("ledger.append", input.idempotencyKey, entry);
  }

  balance(accountId: string): Record<string, string> {
    const totals = new Map<string, bigint>();
    for (const event of this.events.all()) {
      if (event.type !== "ledger.append" || event.payload.accountId !== accountId) continue;
      const asset = String(event.payload.asset);
      const current = totals.get(asset) ?? 0n;
      totals.set(asset, current + decimalToUnits(String(event.payload.delta)));
    }
    return Object.fromEntries([...totals.entries()].map(([asset, units]) => [asset, unitsToDecimal(units)]));
  }

  private findSettlementPayload(transactionId: string): Record<string, unknown> | undefined {
    const event = this.eventsFor(transactionId).find((candidate) => candidate.type === "settlement.initiated");
    return event?.payload;
  }

  private findAccountId(transactionId: string): string | undefined {
    const event = this.eventsFor(transactionId).find((candidate) => candidate.type === "execution.intent_created" || candidate.type === "orders.created");
    return typeof event?.payload.accountId === "string" ? event.payload.accountId : undefined;
  }

  private eventsFor(transactionId: string): DomainEvent[] {
    return this.events.byTransaction(transactionId);
  }
}

function negateDecimal(value: string): string {
  return value.startsWith("-") ? value.slice(1) : `-${value}`;
}

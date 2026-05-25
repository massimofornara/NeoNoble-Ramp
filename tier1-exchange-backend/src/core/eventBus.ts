import { randomUUID } from "node:crypto";
import type { DomainEvent, EventBus, EventType } from "./types.js";
import type { ConsumerOffsetStore, DeadLetterStore, EventStore, ProcessedEventStore } from "./store.js";
import { logJson, metrics } from "./observability.js";

type Handler = (event: DomainEvent) => Promise<void>;

interface Subscriber {
  consumerGroup: string;
  handler: Handler;
  processedEventIds: Set<string>;
}

export class KafkaCompatibleEventStream implements EventBus {
  private readonly subscribers = new Map<EventType, Subscriber[]>();
  private readonly pending = new Set<Promise<void>>();
  private readonly transactionDispatch = new Map<string, Promise<void>>();

  constructor(
    private readonly eventStore: EventStore,
    private readonly deadLetters: DeadLetterStore,
    private readonly offsets: ConsumerOffsetStore,
    private readonly processedEvents: ProcessedEventStore,
    private readonly maxAttempts = 3,
  ) {}

  async publish<TPayload extends Record<string, unknown>>(
    type: EventType,
    transactionId: string,
    payload: TPayload,
  ): Promise<DomainEvent<TPayload>> {
    const event: DomainEvent<TPayload> = {
      eventId: randomUUID(),
      type,
      transactionId,
      timestamp: new Date().toISOString(),
      topic: "exchange.events",
      key: transactionId,
      payload,
    };
    const persisted = await this.eventStore.append(event);
    metrics.inc("exchange_event_throughput_total", { type });
    logJson("event-stream", "event_published", {
      broker: "kafka-compatible-file-log",
      event: persisted,
      correlationId: persisted.transactionId,
      traceId: persisted.transactionId.replace(/-/g, "").slice(0, 32),
    });

    const previous = this.transactionDispatch.get(transactionId) ?? Promise.resolve();
    const dispatch = previous
      .catch(() => undefined)
      .then(() => this.dispatch(persisted))
      .finally(() => {
        if (this.transactionDispatch.get(transactionId) === dispatch) {
          this.transactionDispatch.delete(transactionId);
        }
        this.pending.delete(dispatch);
      });
    this.transactionDispatch.set(transactionId, dispatch);
    this.pending.add(dispatch);
    return persisted as DomainEvent<TPayload>;
  }

  async append<TPayload extends Record<string, unknown>>(
    type: EventType,
    transactionId: string,
    payload: TPayload,
  ): Promise<DomainEvent<TPayload>> {
    return this.publish(type, transactionId, payload);
  }

  async emit<TPayload extends Record<string, unknown>>(
    type: EventType,
    transactionId: string,
    payload: TPayload,
  ): Promise<DomainEvent<TPayload>> {
    return this.publish(type, transactionId, payload);
  }

  subscribe(type: EventType, consumerGroup: string, handler: Handler): void {
    const subscribers = this.subscribers.get(type) ?? [];
    subscribers.push({ consumerGroup, handler, processedEventIds: new Set() });
    this.subscribers.set(type, subscribers);
  }

  async drain(): Promise<void> {
    while (this.pending.size > 0) {
      await Promise.all([...this.pending]);
    }
  }

  async replayAll(): Promise<void> {
    const started = Date.now();
    const events = this.eventStore.all().sort((a, b) => Number(a.offset ?? 0) - Number(b.offset ?? 0));
    for (const event of events) {
      await this.dispatch(event);
    }
    await this.drain();
    metrics.observe("exchange_replay_duration_ms", Date.now() - started);
  }

  private async dispatch(event: DomainEvent): Promise<void> {
    const subscribers = this.subscribers.get(event.type) ?? [];
    const groups = new Map<string, Subscriber[]>();
    for (const subscriber of subscribers) {
      groups.set(subscriber.consumerGroup, [...(groups.get(subscriber.consumerGroup) ?? []), subscriber]);
    }
    for (const groupSubscribers of groups.values()) {
      await this.invokeConsumerGroup(groupSubscribers, event);
    }
  }

  private async invokeConsumerGroup(subscribers: Subscriber[], event: DomainEvent): Promise<void> {
    let lastError: unknown;
    for (const subscriber of subscribers) {
      try {
        await this.invokeSubscriber(subscriber, event);
        return;
      } catch (error) {
        lastError = error;
      }
    }
    if (lastError) throw lastError;
  }

  private async invokeSubscriber(subscriber: Subscriber, event: DomainEvent): Promise<void> {
    if (subscriber.processedEventIds.has(event.eventId)) return;
    if (this.processedEvents.has(subscriber.consumerGroup, event.eventId)) return;
    const eventOffset = Number(event.offset ?? -1);
    const committedOffset = this.offsets.get(subscriber.consumerGroup);
    if (eventOffset >= 0 && eventOffset <= committedOffset) return;

    for (let attempt = 1; attempt <= this.maxAttempts; attempt += 1) {
      try {
        await subscriber.handler(event);
        subscriber.processedEventIds.add(event.eventId);
        await this.processedEvents.mark(subscriber.consumerGroup, event.eventId);
        if (eventOffset >= 0) await this.offsets.set(subscriber.consumerGroup, eventOffset);
        return;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.error(
          JSON.stringify({
            level: "warn",
            component: "event-consumer",
            consumerGroup: subscriber.consumerGroup,
            eventId: event.eventId,
            offset: event.offset,
            attempt,
            error: message,
          }),
        );
        if (attempt === this.maxAttempts) {
          this.deadLetters.append({
            event,
            consumerName: subscriber.consumerGroup,
            error: message,
            attempts: attempt,
          });
          metrics.inc("exchange_dlq_total", { consumerGroup: subscriber.consumerGroup, eventType: event.type });
        }
        await new Promise((resolve) => setTimeout(resolve, attempt * 25));
      }
    }
    throw new Error(`Consumer group ${subscriber.consumerGroup} failed event ${event.eventId}`);
  }
}

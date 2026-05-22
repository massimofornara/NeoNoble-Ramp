import { randomUUID } from "node:crypto";

export class EventBus {
  constructor(store) {
    this.store = store;
    this.events = [];
    this.subscribers = new Map();
  }

  publish(type, payload = {}, metadata = {}) {
    const event = {
      id: randomUUID(),
      type,
      payload,
      metadata,
      createdAt: new Date().toISOString()
    };
    this.events.push(event);
    this.store?.saveEvent(event);
    for (const handler of this.subscribers.get(type) ?? []) {
      handler(event);
    }
    for (const handler of this.subscribers.get("*") ?? []) {
      handler(event);
    }
    return event;
  }

  subscribe(type, handler) {
    const handlers = this.subscribers.get(type) ?? [];
    handlers.push(handler);
    this.subscribers.set(type, handlers);
  }

  tail(limit = 100) {
    return this.events.slice(Math.max(0, this.events.length - limit));
  }
}

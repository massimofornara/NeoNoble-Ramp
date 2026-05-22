import { createHmac, randomUUID } from "node:crypto";

export class WebhookService {
  constructor({ eventBus, developerPlatform, secret = "metaswap-webhooks" }) {
    this.eventBus = eventBus;
    this.developerPlatform = developerPlatform;
    this.secret = secret;
    this.subscriptions = [];
    this.deliveries = [];
    this.eventBus.subscribe("*", (event) => this.enqueue(event));
  }

  subscribe({ apiKey, customerId, url, events = ["*"], label = "default" }) {
    const auth = apiKey ? this.developerPlatform.authorize({ apiKey, route: "webhooks.subscribe", units: 10 }) : { allowed: Boolean(customerId) };
    if (!auth.allowed) throw new Error(auth.reason ?? "Webhook authorization failed");
    if (!url || !/^https:\/\//i.test(url)) throw new Error("Webhook URL must be HTTPS");
    const subscription = {
      id: randomUUID(),
      customerId: customerId ?? auth.apiKey.customerId,
      label,
      url,
      events,
      status: "active",
      createdAt: new Date().toISOString()
    };
    this.subscriptions.push(subscription);
    this.eventBus.publish("WebhookSubscriptionCreated", { ...subscription, url: redactUrl(url) });
    return subscription;
  }

  enqueue(event) {
    for (const subscription of this.subscriptions) {
      if (subscription.status !== "active") continue;
      if (!subscription.events.includes("*") && !subscription.events.includes(event.type)) continue;
      const payload = {
        id: randomUUID(),
        subscriptionId: subscription.id,
        eventId: event.id,
        eventType: event.type,
        status: "queued",
        url: subscription.url,
        body: event,
        signature: this.sign(event),
        createdAt: new Date().toISOString()
      };
      this.deliveries.push(payload);
    }
  }

  async flush({ max = 25 } = {}) {
    const rows = this.deliveries.filter((delivery) => delivery.status === "queued").slice(0, max);
    const results = [];
    for (const delivery of rows) {
      try {
        const response = await fetch(delivery.url, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-metaswap-signature": delivery.signature,
            "x-metaswap-event": delivery.eventType
          },
          body: JSON.stringify(delivery.body)
        });
        delivery.status = response.ok ? "delivered" : "failed";
        delivery.httpStatus = response.status;
      } catch (error) {
        delivery.status = "failed";
        delivery.error = error.message;
      }
      delivery.deliveredAt = new Date().toISOString();
      results.push(delivery);
    }
    return { flushed: results.length, results };
  }

  summary() {
    return {
      generatedAt: new Date().toISOString(),
      subscriptionCount: this.subscriptions.length,
      deliveryCount: this.deliveries.length,
      queued: this.deliveries.filter((row) => row.status === "queued").length,
      delivered: this.deliveries.filter((row) => row.status === "delivered").length,
      failed: this.deliveries.filter((row) => row.status === "failed").length
    };
  }

  sign(event) {
    return createHmac("sha256", this.secret).update(JSON.stringify(event)).digest("hex");
  }
}

function redactUrl(url) {
  try {
    const parsed = new URL(url);
    return `${parsed.origin}${parsed.pathname}`;
  } catch {
    return "invalid";
  }
}

import { createHmac, randomUUID } from "node:crypto";

export class SecretLifecycle {
  constructor({ masterKey, eventBus }) {
    if (!masterKey) throw new Error("Secret lifecycle master key is required");
    this.masterKey = masterKey;
    this.eventBus = eventBus;
    this.records = new Map();
  }

  seal({ name, value, rotationDays = 90 }) {
    const version = randomUUID();
    const digest = createHmac("sha256", this.masterKey).update(value).digest("hex");
    const record = {
      name,
      version,
      digest,
      rotationDays,
      createdAt: new Date().toISOString(),
      nextRotationAt: new Date(Date.now() + rotationDays * 86400_000).toISOString()
    };
    this.records.set(name, record);
    this.eventBus.publish("SecretSealed", { name, version, nextRotationAt: record.nextRotationAt });
    return record;
  }

  rotate({ name, value }) {
    if (!this.records.has(name)) throw new Error("Secret record not found");
    return this.seal({ name, value, rotationDays: this.records.get(name).rotationDays });
  }

  status() {
    return [...this.records.values()].map((record) => ({
      name: record.name,
      version: record.version,
      nextRotationAt: record.nextRotationAt
    }));
  }
}

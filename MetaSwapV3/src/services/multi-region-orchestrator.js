export class MultiRegionOrchestrator {
  constructor({ eventBus, regions = [] }) {
    this.eventBus = eventBus;
    this.regions = new Map(regions.map((region) => [region.id, { status: "active", priority: 100, ...region }]));
  }

  register({ id, role = "active", priority = 100, endpoint }) {
    const region = { id, role, priority, endpoint, status: "active", updatedAt: new Date().toISOString() };
    this.regions.set(id, region);
    this.eventBus.publish("RegionRegistered", region);
    return region;
  }

  failover({ fromRegion, reason }) {
    const failed = this.regions.get(fromRegion);
    if (!failed) throw new Error("Region not found");
    failed.status = "failed";
    failed.reason = reason;
    const target = [...this.regions.values()]
      .filter((region) => region.status === "active" && region.id !== fromRegion)
      .sort((a, b) => a.priority - b.priority)[0];
    if (!target) throw new Error("No active failover region");
    this.eventBus.publish("RegionFailoverExecuted", { fromRegion, toRegion: target.id, reason });
    return { fromRegion, toRegion: target.id, reason };
  }

  status() {
    return [...this.regions.values()];
  }
}

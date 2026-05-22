import { randomUUID } from "node:crypto";

export class IncidentResponse {
  constructor({ eventBus, adminControlPlane }) {
    this.eventBus = eventBus;
    this.adminControlPlane = adminControlPlane;
    this.incidents = [];
  }

  trigger({ severity = "high", type, subject, action = "halt_market", market, reason }) {
    const incident = {
      id: randomUUID(),
      severity,
      type,
      subject,
      action,
      market,
      reason,
      status: "open",
      createdAt: new Date().toISOString()
    };
    if (action === "halt_market" && market) {
      incident.actionResult = this.adminControlPlane.haltMarket({ market, reason: reason ?? type });
    }
    this.incidents.push(incident);
    this.eventBus.publish("SocIncidentTriggered", incident);
    return incident;
  }

  close({ incidentId, resolution }) {
    const incident = this.incidents.find((row) => row.id === incidentId);
    if (!incident) throw new Error("Incident not found");
    incident.status = "closed";
    incident.resolution = resolution;
    incident.closedAt = new Date().toISOString();
    this.eventBus.publish("SocIncidentClosed", incident);
    return incident;
  }
}

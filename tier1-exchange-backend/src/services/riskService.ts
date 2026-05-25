import { decimalToUnits } from "../core/store.js";
import type { EventStore } from "../core/store.js";

export interface RiskCheckInput {
  userId: string;
  asset: string;
  notional: string;
}

export interface RiskStatus {
  circuitOpen: boolean;
  userRiskScore: number;
  userExposureLimit: string;
  assetExposureLimit: string;
  velocityWindowMs: number;
  velocityMaxOrders: number;
}

export class RiskService {
  constructor(
    private readonly events: EventStore,
    private readonly userExposureLimit = decimalToUnits(process.env.USER_EXPOSURE_LIMIT ?? "10000000"),
    private readonly assetExposureLimit = decimalToUnits(process.env.ASSET_EXPOSURE_LIMIT ?? "10000000"),
    private readonly velocityWindowMs = Number(process.env.RISK_VELOCITY_WINDOW_MS ?? 60_000),
    private readonly velocityMaxOrders = Number(process.env.RISK_VELOCITY_MAX_ORDERS ?? 20),
    private readonly singleExecutionAbnormalThreshold = decimalToUnits(process.env.RISK_SINGLE_EXECUTION_THRESHOLD ?? "2500000"),
  ) {}

  assertAllowed(input: RiskCheckInput): void {
    const status = this.status(input.userId);
    if (status.circuitOpen) {
      throw new Error("Risk circuit breaker is open");
    }
    const now = Date.now();
    const notional = decimalToUnits(input.notional);
    const events = this.events.all().filter((event) => event.type === "orders.created");
    const userEvents = events.filter((event) => event.payload.accountId === input.userId || event.payload.userId === input.userId);
    const assetEvents = events.filter((event) => event.payload.toAsset === input.asset || event.payload.toToken === input.asset);
    const windowEvents = userEvents.filter((event) => now - Date.parse(event.timestamp) <= this.velocityWindowMs);

    const userExposure = userEvents.reduce((sum, event) => sum + decimalToUnits(String(event.payload.expectedToAmount ?? "0")), 0n);
    const assetExposure = assetEvents.reduce((sum, event) => sum + decimalToUnits(String(event.payload.expectedToAmount ?? "0")), 0n);

    const dynamicUserLimit = this.dynamicUserExposureLimit(input.userId);
    const dynamicAssetLimit = this.dynamicAssetExposureLimit(input.asset);

    if (notional > this.singleExecutionAbnormalThreshold) {
      throw new Error("Risk limit exceeded: abnormal single execution notional");
    }
    if (userExposure + notional > dynamicUserLimit) {
      throw new Error("Risk limit exceeded: per-user exposure cap");
    }
    if (assetExposure + notional > dynamicAssetLimit) {
      throw new Error("Risk limit exceeded: per-asset exposure cap");
    }
    if (windowEvents.length >= this.velocityMaxOrders) {
      throw new Error("Risk limit exceeded: velocity window");
    }
  }

  status(userId: string): RiskStatus {
    const score = this.accountRiskScore(userId);
    return {
      circuitOpen: this.events.all().some((event) => event.type === "risk.circuit.opened"),
      userRiskScore: score,
      userExposureLimit: this.formatUnits(this.dynamicUserExposureLimit(userId)),
      assetExposureLimit: this.formatUnits(this.assetExposureLimit),
      velocityWindowMs: this.velocityWindowMs,
      velocityMaxOrders: this.velocityMaxOrders,
    };
  }

  private accountRiskScore(userId: string): number {
    const orders = this.events
      .all()
      .filter((event) => event.type === "orders.created" && (event.payload.accountId === userId || event.payload.userId === userId));
    const recentFailures = this.events
      .all()
      .filter((event) => event.type === "reconciliation.requested" && Date.now() - Date.parse(event.timestamp) <= this.velocityWindowMs).length;
    return Math.min(100, orders.length * 2 + recentFailures);
  }

  private dynamicUserExposureLimit(userId: string): bigint {
    const riskScore = this.accountRiskScore(userId);
    if (riskScore >= 80) return this.userExposureLimit / 4n;
    if (riskScore >= 50) return this.userExposureLimit / 2n;
    return this.userExposureLimit;
  }

  private dynamicAssetExposureLimit(asset: string): bigint {
    const concentration = this.events
      .all()
      .filter((event) => event.type === "orders.created" && event.payload.toAsset === asset)
      .reduce((sum, event) => sum + decimalToUnits(String(event.payload.expectedToAmount ?? "0")), 0n);
    return concentration > this.assetExposureLimit / 2n ? (this.assetExposureLimit * 3n) / 4n : this.assetExposureLimit;
  }

  private formatUnits(units: bigint): string {
    const negative = units < 0n;
    const absolute = negative ? -units : units;
    const whole = absolute / 100000000n;
    const fraction = (absolute % 100000000n).toString().padStart(8, "0").replace(/0+$/, "");
    return `${negative ? "-" : ""}${whole.toString()}${fraction ? `.${fraction}` : ""}`;
  }
}

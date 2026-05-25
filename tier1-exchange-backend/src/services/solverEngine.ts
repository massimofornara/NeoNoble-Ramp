import type { DomainEvent, EventBus } from "../core/types.js";
import type { ExecutionPlan } from "./executionPlanner.js";

export interface ScheduledIntent {
  intentId: string;
  traceId: string;
  status: "scheduled";
  route: string[];
  twap: boolean;
  executionPlan: ExecutionPlan;
}

export class SolverEngine {
  constructor(private readonly bus: EventBus) {}

  async scheduleIntent(intent: DomainEvent, executionPlan: ExecutionPlan): Promise<ScheduledIntent> {
    const traceId = String(intent.payload.traceId ?? "");
    await this.bus.publish("execution.scheduled", intent.transactionId, {
      ...intent.payload,
      intentId: intent.transactionId,
      traceId,
      status: "scheduled",
      solver: {
        mode: "intent-based",
        solverId: "internal-solver-v1",
        fallbackOrder: executionPlan.solverFallbacks,
      },
      executionPlan,
    });
    return {
      intentId: intent.transactionId,
      traceId,
      status: "scheduled",
      route: executionPlan.route,
      twap: executionPlan.twap,
      executionPlan,
    };
  }
}

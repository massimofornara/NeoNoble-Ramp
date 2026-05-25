import type { DomainEvent, EventType, TransactionState } from "./types.js";

export function rebuildState(events: DomainEvent[]): { state: TransactionState | "PENDING"; valid: boolean; errors: string[] } {
  let cursor = -1;
  let currentState: TransactionState | "PENDING" = "PENDING";
  const errors: string[] = [];
  let terminalFailed = false;
  let terminalState: TransactionState | undefined;

  for (const event of events) {
    const next = transitionFor(event);
    if (event.type === "execution.failed") {
      if (cursor > 2) {
        errors.push(`Invalid transition: execution.failed arrived after ${stateForIndex(cursor)}`);
      }
      terminalFailed = true;
      terminalState = "EXECUTION_FAILED";
      continue;
    }
    if (event.type === "settlement.failed") {
      if (cursor < 4) {
        errors.push("Missing settlement.initiated before settlement.failed");
      }
      terminalFailed = true;
      terminalState = "SETTLEMENT_FAILED";
      continue;
    }
    if (terminalFailed) {
      errors.push(`Invalid transition: ${event.type} arrived after ${terminalState}`);
      continue;
    }
    const nextIndex = next.index;
    if (nextIndex === -1) continue;
    if (nextIndex < cursor) {
      errors.push(`Invalid transition: ${event.type} arrived after ${stateForIndex(cursor)}`);
    }
    if (nextIndex > cursor + 1 && !(cursor === 0 && (event.type === "execution.requested" || event.type === "execution.started"))) {
      errors.push(`Missing transition before ${event.type}`);
    }
    cursor = Math.max(cursor, nextIndex);
    currentState = next.state;
  }

  return {
    state: terminalFailed ? (terminalState ?? "EXECUTION_FAILED") : cursor >= 0 ? currentState : "PENDING",
    valid: errors.length === 0,
    errors,
  };
}

export function hasEvent(events: DomainEvent[], type: EventType): boolean {
  return events.some((event) => event.type === type);
}

function transitionFor(event: DomainEvent): { index: number; state: TransactionState | "PENDING" } {
  switch (event.type) {
    case "execution.intent_created":
      return { index: 0, state: "INTENT_CREATED" };
    case "execution.scheduled":
      return { index: 1, state: "SCHEDULED" };
    case "orders.created":
      return { index: 0, state: "CREATED" };
    case "execution.requested":
      return { index: 2, state: "EXECUTING" };
    case "execution.started":
      return { index: 2, state: "EXECUTING" };
    case "execution.completed":
      return { index: 3, state: event.payload.type === "offramp" ? "OFFRAMP_EXECUTED" : "SWAP_EXECUTED" };
    case "settlement.initiated":
      return { index: 4, state: "SETTLEMENT_INITIATED" };
    case "settlement.pending_confirmation":
      return { index: 5, state: "SETTLEMENT_PENDING_CONFIRMATION" };
    case "settlement.confirmed":
      return { index: 6, state: "SETTLEMENT_CONFIRMED" };
    case "ledger.append":
      return { index: 7, state: "RECONCILED" };
    default:
      return { index: -1, state: "PENDING" };
  }
}

function stateForIndex(index: number): TransactionState {
  switch (index) {
    case 0:
      return "INTENT_CREATED";
    case 1:
      return "SCHEDULED";
    case 2:
      return "EXECUTING";
    case 3:
      return "SWAP_EXECUTED";
    case 4:
      return "SETTLEMENT_INITIATED";
    case 5:
      return "SETTLEMENT_PENDING_CONFIRMATION";
    case 6:
      return "SETTLEMENT_CONFIRMED";
    default:
      return "RECONCILED";
  }
}

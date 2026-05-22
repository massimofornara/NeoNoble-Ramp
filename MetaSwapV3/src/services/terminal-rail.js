import { createHmac, createHash, randomUUID } from "node:crypto";

export class TerminalRail {
  constructor({ name, secret = "metaswap-terminal-rail-key", eventBus }) {
    this.name = name;
    this.secret = secret;
    this.eventBus = eventBus;
    this.instructions = [];
  }

  createInstruction({ method, path, payload }) {
    const canonicalPayload = JSON.stringify(payload);
    const digest = createHash("sha256").update(`${this.name}:${method}:${path}:${canonicalPayload}`).digest("hex");
    const signature = createHmac("sha256", this.secret).update(digest).digest("hex");
    const instruction = {
      id: randomUUID(),
      rail: this.name,
      method,
      path,
      payload,
      digest,
      signature,
      status: "terminal_instruction_created",
      createdAt: new Date().toISOString()
    };
    this.instructions.push(instruction);
    this.eventBus?.publish("TerminalRailInstructionCreated", instruction);
    return instruction;
  }
}

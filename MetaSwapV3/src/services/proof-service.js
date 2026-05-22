import { createHash } from "node:crypto";

export class ProofService {
  constructor({ ledger }) {
    this.ledger = ledger;
  }

  reservesAndLiabilities() {
    const liabilities = [];
    const reserves = [];
    for (const [accountId, account] of this.ledger.accounts.entries()) {
      const balance = this.ledger.balance(accountId);
      const row = { accountId, asset: account.asset, available: balance.available, locked: balance.locked, pending: balance.pending };
      if (account.ownerType === "customer") liabilities.push(row);
      if (account.ownerType === "platform" && ["inventory", "treasury", "bank", "psp"].includes(account.ownerId)) reserves.push(row);
    }
    return {
      generatedAt: new Date().toISOString(),
      liabilityRoot: this.root(liabilities),
      reserveRoot: this.root(reserves),
      liabilities,
      reserves
    };
  }

  root(rows) {
    const leaves = rows.map((row) => createHash("sha256").update(JSON.stringify(row)).digest("hex")).sort();
    return createHash("sha256").update(leaves.join("")).digest("hex");
  }
}

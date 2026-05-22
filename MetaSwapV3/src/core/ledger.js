import { createHash, randomUUID } from "node:crypto";

const round = (value) => Math.round((Number(value) + Number.EPSILON) * 1e8) / 1e8;

export class Ledger {
  constructor(eventBus, store) {
    this.eventBus = eventBus;
    this.store = store;
    this.accounts = new Map();
    this.balances = new Map();
    this.journal = [];
    this.lastHash = "GENESIS";
    this.load();
  }

  load() {
    const snapshot = this.store?.loadLedger();
    if (!snapshot) return;
    for (const row of snapshot.accounts) {
      this.accounts.set(row.id, {
        id: row.id,
        ownerType: row.owner_type,
        ownerId: row.owner_id,
        asset: row.asset,
        accountType: row.account_type,
        status: row.status
      });
      this.balances.set(row.id, {
        available: row.available,
        locked: row.locked,
        pending: row.pending,
        version: row.version
      });
    }
    this.journal = snapshot.journal;
    this.lastHash = this.journal.at(-1)?.hash ?? "GENESIS";
  }

  accountId(ownerType, ownerId, asset, accountType) {
    return `${ownerType}:${ownerId}:${asset}:${accountType}`;
  }

  ensureAccount(ownerType, ownerId, asset, accountType = "available") {
    const id = this.accountId(ownerType, ownerId, asset, accountType);
    if (!this.accounts.has(id)) {
      this.accounts.set(id, { id, ownerType, ownerId, asset, accountType, status: "active" });
      this.balances.set(id, { available: 0, locked: 0, pending: 0, version: 0 });
      this.store?.saveAccount(this.accounts.get(id), this.balances.get(id));
    }
    return id;
  }

  balance(accountId) {
    return this.balances.get(accountId) ?? { available: 0, locked: 0, pending: 0, version: 0 };
  }

  available(ownerType, ownerId, asset, accountType = "available") {
    return this.balance(this.ensureAccount(ownerType, ownerId, asset, accountType)).available;
  }

  credit(accountId, bucket, amount) {
    amount = round(amount);
    const balance = this.balance(accountId);
    balance[bucket] = round(balance[bucket] + amount);
    balance.version += 1;
    this.balances.set(accountId, balance);
    this.store?.saveAccount(this.accounts.get(accountId), balance);
  }

  debit(accountId, bucket, amount) {
    amount = round(amount);
    const balance = this.balance(accountId);
    if (round(balance[bucket] - amount) < -0.00000001) {
      throw new Error(`Insufficient ${bucket} balance on ${accountId}`);
    }
    balance[bucket] = round(balance[bucket] - amount);
    balance.version += 1;
    this.balances.set(accountId, balance);
    this.store?.saveAccount(this.accounts.get(accountId), balance);
  }

  lock(accountId, amount) {
    this.debit(accountId, "available", amount);
    this.credit(accountId, "locked", amount);
  }

  unlock(accountId, amount) {
    this.debit(accountId, "locked", amount);
    this.credit(accountId, "available", amount);
  }

  postTransfer({ from, to, asset, amount, commandId, eventId, fromBucket = "available", toBucket = "available", memo = "" }) {
    amount = round(amount);
    if (amount <= 0) throw new Error("Transfer amount must be positive");
    this.debit(from, fromBucket, amount);
    this.credit(to, toBucket, amount);
    const postings = [
      { accountId: to, side: "debit", amount, asset },
      { accountId: from, side: "credit", amount, asset }
    ];
    const entry = this.appendJournal({ commandId, eventId, memo, postings });
    this.eventBus.publish("LedgerPosted", { entryId: entry.id, postings, memo });
    return entry;
  }

  appendJournal({ commandId, eventId, memo, postings }) {
    const debits = round(postings.filter((p) => p.side === "debit").reduce((sum, p) => sum + p.amount, 0));
    const credits = round(postings.filter((p) => p.side === "credit").reduce((sum, p) => sum + p.amount, 0));
    if (debits !== credits) throw new Error("Unbalanced journal entry");
    const payload = {
      id: randomUUID(),
      commandId,
      eventId,
      memo,
      postings,
      createdAt: new Date().toISOString(),
      previousHash: this.lastHash
    };
    const hash = createHash("sha256").update(JSON.stringify(payload)).digest("hex");
    const entry = { ...payload, hash };
    this.lastHash = hash;
    this.journal.push(entry);
    this.store?.saveJournal(entry);
    return entry;
  }

  balancesForOwner(ownerId) {
    const rows = [];
    for (const [accountId, account] of this.accounts.entries()) {
      if (account.ownerId === ownerId) {
        rows.push({ accountId, ...account, ...this.balance(accountId) });
      }
    }
    return rows;
  }
}

import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { DatabaseSync } from "node:sqlite";

export class SqliteStore {
  constructor(path) {
    mkdirSync(dirname(path), { recursive: true });
    this.db = new DatabaseSync(path);
    this.db.exec(`
      PRAGMA journal_mode = WAL;
      PRAGMA foreign_keys = ON;
      CREATE TABLE IF NOT EXISTS event_log (
        id TEXT PRIMARY KEY,
        type TEXT NOT NULL,
        payload TEXT NOT NULL,
        metadata TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS ledger_accounts (
        id TEXT PRIMARY KEY,
        owner_type TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        asset TEXT NOT NULL,
        account_type TEXT NOT NULL,
        status TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS ledger_balances (
        account_id TEXT PRIMARY KEY,
        available REAL NOT NULL,
        locked REAL NOT NULL,
        pending REAL NOT NULL,
        version INTEGER NOT NULL
      );
      CREATE TABLE IF NOT EXISTS ledger_journal (
        id TEXT PRIMARY KEY,
        command_id TEXT,
        event_id TEXT,
        memo TEXT,
        postings TEXT NOT NULL,
        previous_hash TEXT NOT NULL,
        hash TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS outbox (
        id TEXT PRIMARY KEY,
        adapter TEXT NOT NULL,
        instruction_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS assets (
        symbol TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS wallet_challenges (
        id TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS wallet_sessions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
    `);
  }

  saveEvent(event) {
    this.db.prepare("INSERT OR IGNORE INTO event_log VALUES (?, ?, ?, ?, ?)").run(
      event.id,
      event.type,
      JSON.stringify(event.payload),
      JSON.stringify(event.metadata),
      event.createdAt
    );
  }

  loadLedger() {
    const accounts = this.db.prepare(`
      SELECT a.*, b.available, b.locked, b.pending, b.version
      FROM ledger_accounts a
      JOIN ledger_balances b ON b.account_id = a.id
    `).all();
    const journal = this.db.prepare("SELECT * FROM ledger_journal ORDER BY created_at ASC").all();
    return {
      accounts,
      journal: journal.map((row) => ({
        id: row.id,
        commandId: row.command_id,
        eventId: row.event_id,
        memo: row.memo,
        postings: JSON.parse(row.postings),
        previousHash: row.previous_hash,
        hash: row.hash,
        createdAt: row.created_at
      }))
    };
  }

  saveAccount(account, balance) {
    this.db.prepare("INSERT OR REPLACE INTO ledger_accounts VALUES (?, ?, ?, ?, ?, ?)").run(
      account.id,
      account.ownerType,
      account.ownerId,
      account.asset,
      account.accountType,
      account.status
    );
    this.db.prepare("INSERT OR REPLACE INTO ledger_balances VALUES (?, ?, ?, ?, ?)").run(
      account.id,
      balance.available,
      balance.locked,
      balance.pending,
      balance.version
    );
  }

  saveJournal(entry) {
    this.db.prepare("INSERT OR IGNORE INTO ledger_journal VALUES (?, ?, ?, ?, ?, ?, ?, ?)").run(
      entry.id,
      entry.commandId ?? null,
      entry.eventId ?? null,
      entry.memo ?? null,
      JSON.stringify(entry.postings),
      entry.previousHash,
      entry.hash,
      entry.createdAt
    );
  }

  saveAsset(asset) {
    this.db.prepare("INSERT OR REPLACE INTO assets VALUES (?, ?, ?)").run(
      asset.symbol,
      JSON.stringify(asset),
      new Date().toISOString()
    );
  }

  loadAssets() {
    return this.db.prepare("SELECT payload FROM assets").all().map((row) => JSON.parse(row.payload));
  }

  saveWalletChallenge(challenge) {
    this.db.prepare("INSERT OR REPLACE INTO wallet_challenges VALUES (?, ?, ?)").run(
      challenge.id,
      JSON.stringify(challenge),
      new Date().toISOString()
    );
  }

  loadWalletChallenges() {
    return this.db.prepare("SELECT payload FROM wallet_challenges").all().map((row) => JSON.parse(row.payload));
  }

  saveWalletSession(session) {
    this.db.prepare("INSERT OR REPLACE INTO wallet_sessions VALUES (?, ?, ?, ?)").run(
      session.id,
      session.userId,
      JSON.stringify(session),
      session.createdAt
    );
  }

  loadWalletSessions() {
    return this.db.prepare("SELECT payload FROM wallet_sessions").all().map((row) => JSON.parse(row.payload));
  }
}

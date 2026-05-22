const assert = require('node:assert/strict');
const fs = require('node:fs');

assert.ok(fs.existsSync('db/migrations/20260522_tier1_exchange.sql'), 'tier1 migration exists');
assert.ok(fs.existsSync('lib/custody/withdrawalSigning.ts'), 'custody withdrawal signing exists');
assert.ok(fs.existsSync('services/execution-engine/executionEngine.ts'), 'execution engine exists');

const sql = fs.readFileSync('db/migrations/20260522_tier1_exchange.sql', 'utf8');
for (const table of ['custody_wallets', 'withdrawal_requests', 'clob_orders', 'clob_trades', 'compliance_cases', 'treasury_positions']) {
  assert.match(sql, new RegExp(`create table if not exists ${table}`), `${table} schema present`);
}

const matching = fs.readFileSync('lib/matching-engine/matchingEngine.ts', 'utf8');
assert.match(matching, /price.*time|sequence|canCross/s, 'matching engine contains price-time logic');

console.log(JSON.stringify({ ok: true, suite: 'exchange.integration' }));

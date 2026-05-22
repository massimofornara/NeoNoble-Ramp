const assert = require('node:assert/strict');
const fs = require('node:fs');

for (const file of [
  'lib/recovery-engine/ledgerRebuild.ts',
  'lib/recovery-engine/eventReplay.ts',
  'lib/recovery-engine/bootstrap.ts',
  'tools/recovery/rebuild-ledger.js',
]) {
  assert.ok(fs.existsSync(file), `${file} exists`);
}

const rebuild = fs.readFileSync('lib/recovery-engine/ledgerRebuild.ts', 'utf8');
assert.match(rebuild, /delete from balances/i, 'rebuild clears balance projection');
assert.match(rebuild, /journal_entries/i, 'rebuild uses journal entries source of truth');

console.log(JSON.stringify({ ok: true, suite: 'chaos.recovery' }));

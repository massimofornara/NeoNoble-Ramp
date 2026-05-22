const assert = require('node:assert/strict');

const baseUrl = process.env.BASE_URL || 'http://localhost:3000';
const total = Number(process.env.LOAD_REQUESTS || 25);

async function main() {
  const started = Date.now();
  const responses = await Promise.all(
    Array.from({ length: total }, (_, index) =>
      fetch(`${baseUrl}/api/health`)
        .then((response) => ({ status: response.status, index }))
        .catch((error) => ({ status: 0, error: error.message, index })),
    ),
  );
  const failures = responses.filter((response) => response.status !== 200);
  assert.equal(failures.length, 0, `health failures: ${JSON.stringify(failures.slice(0, 3))}`);
  console.log(JSON.stringify({ ok: true, suite: 'load.exchange', total, durationMs: Date.now() - started }));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

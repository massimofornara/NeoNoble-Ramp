const baseUrl = process.env.RECONCILIATION_BASE_URL || 'http://localhost:3000';
const intervalMs = Number(process.env.RECONCILIATION_INTERVAL_MS || 60000);
const token = process.env.RECONCILIATION_ADMIN_TOKEN || '';

async function runOnce() {
  const response = await fetch(`${baseUrl}/api/exchange/reconcile`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  const body = await response.text();
  const log = {
    level: response.ok ? 'info' : 'error',
    service: 'neonoble-reconciliation-worker',
    time: new Date().toISOString(),
    status: response.status,
    body,
  };
  console.log(JSON.stringify(log));
}

async function loop() {
  for (;;) {
    try {
      await runOnce();
    } catch (error) {
      console.error(JSON.stringify({
        level: 'error',
        service: 'neonoble-reconciliation-worker',
        time: new Date().toISOString(),
        error: error instanceof Error ? error.message : String(error),
      }));
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

void loop();

const baseUrl = process.env.BASE_URL || 'http://localhost:3000';
const token = process.env.RECONCILIATION_ADMIN_TOKEN || '';

async function main() {
  const response = await fetch(`${baseUrl}/api/exchange/recovery`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  const body = await response.text();
  process.stdout.write(`${body}\n`);
  if (!response.ok) process.exit(1);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

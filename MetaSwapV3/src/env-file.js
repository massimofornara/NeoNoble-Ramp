import { existsSync, readFileSync } from "node:fs";

export function loadEnvFile(path = process.env.ENV_PATH ?? ".env.production") {
  if (!path || !existsSync(path)) return { loaded: false, path };
  const rows = readFileSync(path, "utf8").split(/\r?\n/);
  let loaded = 0;
  for (const row of rows) {
    const line = row.trim();
    if (!line || line.startsWith("#")) continue;
    const index = line.indexOf("=");
    if (index < 1) continue;
    const key = line.slice(0, index).trim();
    const value = normalizeEnvValue(line.slice(index + 1));
    if (!process.env[key]) {
      process.env[key] = value;
      loaded += 1;
    }
  }
  return { loaded: true, path, entries: loaded };
}

function normalizeEnvValue(value = "") {
  let normalized = value.trim();
  while (
    (normalized.startsWith('"') && normalized.endsWith('"')) ||
    (normalized.startsWith("'") && normalized.endsWith("'"))
  ) {
    normalized = normalized.slice(1, -1).trim();
  }
  return normalized;
}

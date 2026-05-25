import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(here, "..", "..");
const workspaceRoot = resolve(projectRoot, "..");

loadEnvFile(process.env.TIER1_ENV_FILE);
loadEnvFile(join(workspaceRoot, ".env"));
loadEnvFile(join(projectRoot, ".env"));
loadEnvFile(join(projectRoot, "config", "environments", `${process.env.TIER1_ENV ?? process.env.NODE_ENV ?? ""}.env`));

function loadEnvFile(path: string | undefined): void {
  if (!path || !existsSync(path)) return;
  const contents = readFileSync(path, "utf8");
  for (const rawLine of contents.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const equals = line.indexOf("=");
    if (equals <= 0) continue;
    const key = line.slice(0, equals).trim();
    const value = stripQuotes(line.slice(equals + 1).trim());
    if (!key || process.env[key] !== undefined) continue;
    process.env[key] = value;
  }
}

function stripQuotes(value: string): string {
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1);
  }
  return value;
}

import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

export function ensureDir(path: string): void {
  mkdirSync(path, { recursive: true });
}

export function appendJsonLine<T>(filePath: string, value: T): void {
  ensureDir(dirname(filePath));
  appendFileSync(filePath, `${JSON.stringify(value)}\n`, "utf8");
}

export function readJsonLines<T>(filePath: string): T[] {
  if (!existsSync(filePath)) return [];
  return readFileSync(filePath, "utf8")
    .split(/\r?\n/)
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as T);
}

export function readJsonFile<T>(filePath: string, fallback: T): T {
  if (!existsSync(filePath)) return fallback;
  return JSON.parse(readFileSync(filePath, "utf8")) as T;
}

export function atomicWriteJson<T>(filePath: string, value: T): void {
  ensureDir(dirname(filePath));
  const tmp = `${filePath}.tmp`;
  writeFileSync(tmp, JSON.stringify(value, null, 2), "utf8");
  renameSync(tmp, filePath);
}

export class AsyncMutex {
  private current = Promise.resolve();

  async runExclusive<T>(fn: () => Promise<T> | T): Promise<T> {
    const previous = this.current;
    let release!: () => void;
    this.current = new Promise<void>((resolve) => {
      release = resolve;
    });
    await previous;
    try {
      return await fn();
    } finally {
      release();
    }
  }
}

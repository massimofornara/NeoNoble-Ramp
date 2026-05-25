import "../core/env.js";
import type { AddressInfo } from "node:net";
import { createApiServer } from "../api/server.js";

async function main() {
  const { server } = createApiServer();
  await new Promise<void>((resolve) => server.listen(0, resolve));
  const address = server.address() as AddressInfo;
  const baseUrl = `http://127.0.0.1:${address.port}`;

  try {
    const preflight = (await get(baseUrl, "/production/preflight")) as { ready?: boolean; checks?: unknown[] };
    if (!preflight.ready) {
      console.log(
        JSON.stringify(
          {
            mode: "real-demo",
            status: "failed",
            reason: "production preflight is not ready; no placeholder settlement was executed",
            preflight,
          },
          null,
          2,
        ),
      );
      return;
    }

    const swap = await post(baseUrl, "/production/execute-real-swap", "demo-real-swap-0001", {
      userId: "massi-prod-001",
      fromToken: "NENO",
      toToken: "WBNB",
      amount: "100",
      executionMode: "real",
      gasStrategy: "low_cost",
    });

    const offramp = await post(baseUrl, "/offramp", "demo-real-offramp-0001", {
      userId: "massi-prod-001",
      fromToken: "NENO",
      amount: "200",
      fiatCurrency: "EUR",
      rate: "20000",
      executionMode: "real",
    });

    console.log(
      JSON.stringify(
        {
          mode: "real-demo",
          swap,
          offramp,
        },
        null,
        2,
      ),
    );
  } finally {
    server.close();
  }
}

async function get(baseUrl: string, path: string) {
  const response = await fetch(`${baseUrl}${path}`);
  return response.json() as Promise<Record<string, unknown>>;
}

async function post(baseUrl: string, path: string, idempotencyKey: string, body: Record<string, unknown>) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "idempotency-key": idempotencyKey,
    },
    body: JSON.stringify(body),
  });
  const payload = (await response.json()) as Record<string, unknown>;
  if (!response.ok) {
    throw new Error(`${path} failed: ${response.status} ${JSON.stringify(payload)}`);
  }
  return payload;
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

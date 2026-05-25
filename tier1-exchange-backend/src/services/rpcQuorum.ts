export interface RpcReceipt {
  status?: string;
  blockNumber?: string;
  transactionHash?: string;
  [key: string]: unknown;
}

export interface RpcTransaction {
  hash?: string;
  blockHash?: string | null;
  blockNumber?: string | null;
  nonce?: string;
  from?: string;
  [key: string]: unknown;
}

export class RpcQuorum {
  constructor(private readonly urls = rpcUrls()) {}

  async receipt(txHash: string): Promise<{ receipt?: RpcReceipt; quorum: number; responses: RpcReceipt[] }> {
    if (this.urls.length === 0) throw new Error("RPC quorum has no configured RPC URLs");
    const settled = await Promise.allSettled(this.urls.map((url) => rpc<RpcReceipt | null>(url, "eth_getTransactionReceipt", [txHash])));
    const responses = settled
      .filter((result): result is PromiseFulfilledResult<RpcReceipt | null> => result.status === "fulfilled")
      .map((result) => result.value)
      .filter((receipt): receipt is RpcReceipt => Boolean(receipt));
    const quorum = Math.floor(this.urls.length / 2) + 1;
    return { receipt: quorumReceipt(responses, quorum), quorum, responses };
  }

  async transaction(txHash: string): Promise<{ transaction?: RpcTransaction; quorum: number; responses: RpcTransaction[] }> {
    if (this.urls.length === 0) throw new Error("RPC quorum has no configured RPC URLs");
    const settled = await Promise.allSettled(this.urls.map((url) => rpc<RpcTransaction | null>(url, "eth_getTransactionByHash", [txHash])));
    const responses = settled
      .filter((result): result is PromiseFulfilledResult<RpcTransaction | null> => result.status === "fulfilled")
      .map((result) => result.value)
      .filter((transaction): transaction is RpcTransaction => Boolean(transaction));
    const quorum = Math.floor(this.urls.length / 2) + 1;
    return { transaction: responses.length >= quorum ? responses[0] : undefined, quorum, responses };
  }

  async blockNumber(): Promise<number> {
    const settled = await Promise.allSettled(this.urls.map((url) => rpc<string>(url, "eth_blockNumber", [])));
    const values = settled
      .filter((result): result is PromiseFulfilledResult<string> => result.status === "fulfilled")
      .map((result) => Number.parseInt(result.value.slice(2), 16))
      .filter(Number.isFinite);
    if (values.length === 0) throw new Error("RPC quorum could not fetch latest block");
    return Math.min(...values);
  }
}

function quorumReceipt(responses: RpcReceipt[], quorum: number): RpcReceipt | undefined {
  const counts = new Map<string, { receipt: RpcReceipt; count: number }>();
  for (const receipt of responses) {
    const key = `${String(receipt.transactionHash ?? "").toLowerCase()}:${String(receipt.blockNumber ?? "")}:${String(receipt.status ?? "").toLowerCase()}`;
    const current = counts.get(key);
    counts.set(key, { receipt, count: (current?.count ?? 0) + 1 });
  }
  return [...counts.values()].find((item) => item.count >= quorum)?.receipt;
}

async function rpc<T>(url: string, method: string, params: unknown[]): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: `${Date.now()}:${method}`, method, params }),
  });
  const body = (await response.json()) as { result?: T; error?: { message?: string } };
  if (!response.ok || body.error) throw new Error(body.error?.message ?? `${method} failed with ${response.status}`);
  return body.result as T;
}

function rpcUrls(): string[] {
  return [
    process.env.BSC_RPC_URL,
    ...(process.env.BSC_RPC_URLS ? process.env.BSC_RPC_URLS.split(",").map((value) => value.trim()) : []),
  ].filter((value): value is string => Boolean(value));
}

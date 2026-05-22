import { keccak256Hex } from "../crypto/keccak256.js";

export class BlockchainEventListener {
  constructor({ blockchainAdapters, eventBus, ledger }) {
    this.blockchainAdapters = blockchainAdapters;
    this.eventBus = eventBus;
    this.ledger = ledger;
  }

  async scanDeposits({ chain, address, tokenAddress, fromBlock = "earliest", toBlock = "latest" }) {
    const adapter = this.blockchainAdapters[chain];
    if (!adapter?.configured()) throw new Error(`RPC is required for ${chain}`);
    const events = adapter.namespace === "solana"
      ? await this.scanSolana(adapter, address)
      : await this.scanEvm(adapter, { address, tokenAddress, fromBlock, toBlock });
    this.eventBus.publish("BlockchainDepositsScanned", { chain, address, count: events.length });
    return { chain, address, events };
  }

  async scanEvm(adapter, { address, tokenAddress, fromBlock, toBlock }) {
    if (!tokenAddress) {
      return [{ type: "native_balance_observed", balance: await adapter.nativeBalance(address) }];
    }
    const topic0 = `0x${keccak256Hex("Transfer(address,address,uint256)")}`;
    const topicTo = `0x${address.toLowerCase().replace("0x", "").padStart(64, "0")}`;
    return await adapter.call("eth_getLogs", [{
      address: tokenAddress,
      fromBlock,
      toBlock,
      topics: [topic0, null, topicTo]
    }]);
  }

  async syncDeposits({ userId, chain, custodyAddress, address = custodyAddress, tokenAddress, symbol, decimals = 18, fromBlock = "earliest", toBlock = "latest" }) {
    if (!this.ledger) throw new Error("Ledger is required for on-chain deposit sync");
    if (!userId) throw new Error("userId is required");
    if (!symbol) throw new Error("symbol is required");
    if (!tokenAddress) throw new Error("tokenAddress is required");
    const depositAddress = address ?? custodyAddress;
    if (!depositAddress) throw new Error("custodyAddress is required");
    const adapter = this.blockchainAdapters[chain];
    if (!adapter?.configured()) throw new Error(`RPC is required for ${chain}`);
    if (adapter.namespace === "solana") throw new Error("Ledger sync for SPL deposits is not enabled in this endpoint");

    const logs = await this.scanEvm(adapter, { address: depositAddress, tokenAddress, fromBlock, toBlock });
    const credited = [];
    const skipped = [];
    for (const log of logs) {
      const key = `${chain}:${log.transactionHash}:${log.logIndex ?? log.transactionIndex ?? "0x0"}`;
      const memo = `onchain deposit ${key}`;
      if (this.ledger.journal.some((entry) => entry.memo === memo)) {
        skipped.push({ key, reason: "already_synced" });
        continue;
      }
      const amount = decodeEvmUint256(log.data) / 10 ** Number(decimals);
      if (amount <= 0) {
        skipped.push({ key, reason: "zero_amount" });
        continue;
      }
      const external = this.ledger.ensureAccount("external", `${chain}-deposit:${depositAddress.toLowerCase()}`, symbol);
      this.ledger.credit(external, "available", amount);
      const customer = this.ledger.ensureAccount("customer", userId, symbol);
      const entry = this.ledger.postTransfer({ from: external, to: customer, asset: symbol, amount, memo });
      credited.push({ key, amount, entryId: entry.id, transactionHash: log.transactionHash, blockNumber: log.blockNumber });
    }
    const result = {
      chain,
      userId,
      symbol,
      tokenAddress,
      depositAddress,
      scanned: logs.length,
      credited,
      skipped,
      creditedAmount: credited.reduce((sum, row) => sum + row.amount, 0)
    };
    this.eventBus.publish("OnChainDepositsSynced", result);
    return result;
  }

  async scanSolana(adapter, address) {
    const signatures = await adapter.call("getSignaturesForAddress", [address, { limit: 100 }]);
    return signatures.map((row) => ({ type: "solana_signature", ...row }));
  }
}

function decodeEvmUint256(value) {
  if (!value || value === "0x") return 0;
  return Number(BigInt(value));
}

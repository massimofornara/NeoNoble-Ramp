import test from "node:test";
import assert from "node:assert/strict";
import { createPlatform } from "../src/platform.js";
import { loadConfig } from "../src/config.js";
import { keccak256Hex } from "../src/crypto/keccak256.js";

test("ledger keeps balanced journal entries", () => {
  const platform = createPlatform({ store: false });
  for (const entry of platform.ledger.journal) {
    const debits = entry.postings.filter((p) => p.side === "debit").reduce((sum, p) => sum + p.amount, 0);
    const credits = entry.postings.filter((p) => p.side === "credit").reduce((sum, p) => sum + p.amount, 0);
    assert.equal(Number(debits.toFixed(8)), Number(credits.toFixed(8)));
    assert.ok(entry.hash);
  }
});

test("creates controlled token and executes RFQ buy/sell against internal liquidity", async () => {
  const platform = createPlatform({ store: false });
  const token = await platform.tokenFactory.createToken({
    issuerId: "issuer-1",
    symbol: "NBL",
    name: "Neo Noble",
    maxSupply: 100_000_000,
    issuePriceUsd: 0.25,
    chains: ["ethereum", "solana"],
    contracts: {
      ethereum: "0x1111111111111111111111111111111111111111",
      solana: "NBL11111111111111111111111111111111111111111"
    },
    micaClassification: "utility"
  });
  assert.equal(token.lifecycle, "rfq");

  const buy = await platform.oms.submitOrder({ userId: "user-eu-1", symbol: "NBL", quoteAsset: "EUR", side: "buy", amount: 1000 });
  assert.equal(buy.status, "filled");
  assert.equal(buy.venue, "rfq");
  assert.ok(platform.ledger.available("customer", "user-eu-1", "NBL") >= 1000);

  const sell = await platform.oms.submitOrder({ userId: "user-eu-1", symbol: "NBL", quoteAsset: "EUR", side: "sell", amount: 100 });
  assert.equal(sell.status, "filled");
});

test("blocks trade when KYC or balance risk gate fails", async () => {
  const platform = createPlatform({ store: false });
  platform.complianceHub.upsertUser({ id: "blocked-user", status: "active", kycTier: "none", jurisdiction: "EU" });
  const result = await platform.oms.submitOrder({ userId: "blocked-user", symbol: "ETH", quoteAsset: "EUR", side: "buy", amount: 1 });
  assert.equal(result.status, "rejected");
  assert.ok(result.risk.reasons.includes("KYC_TIER_TOO_LOW") || result.risk.reasons.includes("INSUFFICIENT_BALANCE"));
});

test("supports fiat deposit and payout reconciliation", async () => {
  const platform = createPlatform({ store: false });
  const deposit = platform.fiatGateway.deposit({ userId: "user-eu-1", asset: "EUR", amount: 1000, rail: "SEPA" });
  assert.equal(deposit.status, "settled");
  const payout = await platform.fiatGateway.payout({
    userId: "user-eu-1",
    asset: "EUR",
    amount: 250,
    rail: "SEPA",
    destination: { iban: "DE89370400440532013000", name: "Demo User" }
  });
  assert.equal(payout.status, "submitted");
  assert.equal(platform.fiatGateway.reconciliation.length, 2);
});

test("captures trading and payout revenue into platform fee accounts", async () => {
  const platform = createPlatform({ store: false });
  await platform.tokenFactory.createToken({
    issuerId: "issuer-1",
    symbol: "REV",
    name: "Revenue Token",
    maxSupply: 1_000_000,
    issuePriceUsd: 1,
    chains: ["ethereum"],
    contracts: { ethereum: "0x2222222222222222222222222222222222222222" }
  });

  const trade = await platform.oms.submitOrder({ userId: "user-eu-1", symbol: "REV", quoteAsset: "EUR", side: "buy", amount: 100 });
  assert.equal(trade.status, "filled");
  assert.ok(trade.trade.fee.feeAmount > 0);
  assert.ok(platform.ledger.available("platform", "fees", "EUR") > 0);

  const payout = await platform.fiatGateway.payout({
    userId: "user-eu-1",
    asset: "EUR",
    amount: 100,
    rail: "SEPA",
    destination: { iban: "DE89370400440532013000", name: "Demo User" }
  });
  assert.ok(payout.fee.feeAmount >= 1.5);
  const summary = platform.revenueEngine.summary();
  assert.ok(summary.capturedRevenueUsd > 0);
  assert.equal(summary.requiredMonthlyVolume.blendedTakeRateBps, 55);
});

test("captures consented growth leads and exposes campaign summary", () => {
  const platform = createPlatform({ store: false });
  const lead = platform.growthEngine.captureLead({
    email: "founder@example.com",
    company: "IssuerCo",
    role: "Founder",
    segment: "token_issuers",
    consent: true,
    budgetUsd: 50000,
    expectedMonthlyVolumeUsd: 2000000
  });
  assert.equal(lead.status, "sales_qualified");
  assert.throws(() => platform.growthEngine.captureLead({ email: "no-consent@example.com" }), /consent/);
  const summary = platform.growthEngine.summary();
  assert.equal(summary.leadCount, 1);
  assert.ok(summary.campaigns.length >= 4);
});

test("meters premium RPC usage and exposes developer monetization", async () => {
  const platform = createPlatform({ store: false });
  platform.onChainSettlement.blockchainAdapters.ethereum = {
    configured: () => true,
    status: () => ({ chainId: "1", providers: [{ url: "local", failures: 0 }] }),
    call: async (method) => method === "eth_blockNumber" ? "0x10" : "0x0",
    broadcast: async () => "0xrelay"
  };
  const api = platform.developerPlatform.registerApiKey({ customerId: "devco", planId: "pro" });
  const rpc = await platform.rpcMonetizationService.rpc({ apiKey: api.apiKey, chain: "ethereum", method: "eth_blockNumber" });
  assert.equal(rpc.result, "0x10");
  const relay = await platform.rpcMonetizationService.relay({ apiKey: api.apiKey, chain: "ethereum", rawTransaction: "0xabc", userConsent: true });
  assert.equal(relay.txHash, "0xrelay");
  const summary = platform.developerPlatform.summary();
  assert.equal(summary.apiKeyCount, 1);
  assert.ok(summary.usageUnits >= 51);
  assert.ok(summary.meteredRevenueUsd > 0);
});

test("self-service developer onboarding returns a trial API dashboard", () => {
  const platform = createPlatform({ store: false });
  const onboarded = platform.developerPlatform.onboard({
    email: "dev@example.com",
    company: "DevCo",
    name: "Dev User",
    expectedMonthlyUnits: 250000,
    consent: true
  });
  assert.match(onboarded.apiKey, /^msv3_/);
  const dashboard = platform.developerPlatform.dashboard({ apiKey: onboarded.apiKey });
  assert.equal(dashboard.customer.email, "dev@example.com");
  assert.equal(dashboard.plan.id, "trial");
});

test("enterprise funnel captures real leads and creates non-recognized proposals", () => {
  const platform = createPlatform({ store: false });
  const lead = platform.enterpriseSalesEngine.captureLead({
    email: "buyer@example.com",
    company: "BuyerCo",
    name: "Buyer",
    role: "Founder",
    packageId: "dedicated-rpc-pool",
    budgetUsd: 25000,
    expectedMonthlyUnits: 75_000_000,
    urgency: "this_week",
    consent: true
  });
  assert.equal(lead.status, "enterprise_sales_qualified");

  const proposal = platform.enterpriseSalesEngine.createProposal({
    leadId: lead.id,
    packageId: "dedicated-rpc-pool",
    expectedMonthlyUnits: 75_000_000
  });
  assert.equal(proposal.monthlyRecurringUsd, 7500);
  assert.equal(proposal.paymentStatus, "unpaid");
  assert.equal(platform.enterpriseSalesEngine.summary().verifiedMrrUsd, 0);

  const payment = platform.enterpriseSalesEngine.recordVerifiedPayment({
    proposalId: proposal.id,
    amountUsd: proposal.firstMonthDueUsd,
    externalReference: "bank-ref-001",
    reconciled: true
  });
  assert.equal(payment.status, "reconciled");
  assert.equal(platform.enterpriseSalesEngine.summary().verifiedMrrUsd, 7500);

  const replica = createPlatform({ store: false });
  const replicaProposal = replica.enterpriseSalesEngine.createProposal({
    leadId: lead.id,
    leadSnapshot: lead,
    packageId: "dedicated-rpc-pool"
  });
  assert.equal(replicaProposal.leadId, lead.id);
});

test("queues signed webhook deliveries for subscribed events", () => {
  const platform = createPlatform({ store: false });
  const api = platform.developerPlatform.registerApiKey({ customerId: "hookco", planId: "pro" });
  const sub = platform.webhookService.subscribe({ apiKey: api.apiKey, url: "https://example.com/metaswap", events: ["GrowthLeadCaptured"] });
  platform.growthEngine.captureLead({ email: "buyer@example.com", consent: true, company: "BuyerCo", role: "CTO", segment: "brokers_fintechs" });
  assert.equal(sub.status, "active");
  assert.equal(platform.webhookService.summary().queued, 1);
});

test("plans compliant revenue distribution to IBAN destinations", async () => {
  const config = loadConfig({
    METASWAP_ENV: "local",
    REVENUE_FIAT_IBAN_1: "IT22B0200822800000103317304",
    REVENUE_FIAT_NAME_1: "Demo Beneficiary Italy",
    REVENUE_FIAT_SHARE_BPS_1: "5000",
    REVENUE_FIAT_IBAN_2: "BE06967614820722",
    REVENUE_FIAT_NAME_2: "Demo Beneficiary Belgium",
    REVENUE_FIAT_SHARE_BPS_2: "5000",
    REVENUE_CRYPTO_WALLET: "0xD436E1FbDFFD0a538D0A44A93c0dD52f92221862",
    ETHEREUM_CHAIN_ID: "1"
  });
  const platform = createPlatform({ store: false, config });
  const external = platform.ledger.ensureAccount("external", "test-revenue", "EUR");
  const fees = platform.ledger.ensureAccount("platform", "fees", "EUR");
  platform.ledger.credit(external, "available", 1000);
  platform.ledger.postTransfer({ from: external, to: fees, asset: "EUR", amount: 1000, memo: "test fee funding" });

  const plan = platform.revenueDistributionEngine.plan();
  assert.equal(plan.status, "ready");
  assert.equal(plan.routes.length, 2);
  const sweep = await platform.revenueDistributionEngine.sweep({ maxAmount: 100 });
  assert.equal(sweep.status, "submitted");
  assert.equal(sweep.executed.length, 2);
  assert.equal(platform.revenueDistributionEngine.distributions.length, 2);
});

test("wallet challenge and token import metadata are wired", async () => {
  const platform = createPlatform({ store: false });
  const token = await platform.tokenFactory.createToken({
    issuerId: "issuer-1",
    symbol: "WLT",
    name: "Wallet Token",
    maxSupply: 1_000_000,
    issuePriceUsd: 1,
    chains: ["ethereum"],
    contracts: { ethereum: "0x3333333333333333333333333333333333333333" }
  });
  const challenge = platform.walletService.createChallenge({
    userId: "user-eu-1",
    address: "0x4444444444444444444444444444444444444444",
    chain: "ethereum",
    walletType: "metamask"
  });
  assert.equal(challenge.chain, "ethereum");
  assert.match(challenge.message, /MetaSwap V3 wallet authentication/);
  const metadata = platform.walletService.tokenImportMetadata(token, "ethereum");
  assert.equal(metadata.evm.method, "wallet_watchAsset");
});

test("token deployment prepare reports missing token fields clearly", async () => {
  const platform = createPlatform({ store: false });
  await assert.rejects(
    () => platform.tokenDeploymentService.prepare({
      userId: "user-eu-1",
      address: "0x4444444444444444444444444444444444444444",
      chain: "ethereum",
      walletType: "eip1193"
    }),
    /Missing token deployment fields: name, symbol, maxSupply/
  );
});

test("syncs confirmed ERC-20 deposits into the ledger idempotently", async () => {
  const platform = createPlatform({ store: false });
  const tokenAddress = "0x5555555555555555555555555555555555555555";
  const custodyAddress = "0x6666666666666666666666666666666666666666";
  const amount = 5n * 10n ** 18n;
  platform.blockchainEventListener.blockchainAdapters.ethereum = {
    namespace: "evm",
    configured: () => true,
    call: async () => [{
      address: tokenAddress,
      transactionHash: "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      logIndex: "0x0",
      blockNumber: "0x1",
      data: `0x${amount.toString(16).padStart(64, "0")}`,
      topics: []
    }]
  };

  const first = await platform.blockchainEventListener.syncDeposits({
    userId: "user-eu-1",
    chain: "ethereum",
    custodyAddress,
    tokenAddress,
    symbol: "DEP",
    decimals: 18
  });
  const second = await platform.blockchainEventListener.syncDeposits({
    userId: "user-eu-1",
    chain: "ethereum",
    custodyAddress,
    tokenAddress,
    symbol: "DEP",
    decimals: 18
  });

  assert.equal(first.creditedAmount, 5);
  assert.equal(second.creditedAmount, 0);
  assert.equal(platform.ledger.available("customer", "user-eu-1", "DEP"), 5);
});

test("keccak256 uses Ethereum digest", () => {
  assert.equal(keccak256Hex(new Uint8Array()), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470");
});

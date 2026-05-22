import { randomUUID } from "node:crypto";

const dayMs = 24 * 60 * 60 * 1000;

export class EnterpriseSalesEngine {
  constructor({ eventBus, developerPlatform, revenueEngine, growthEngine }) {
    this.eventBus = eventBus;
    this.developerPlatform = developerPlatform;
    this.revenueEngine = revenueEngine;
    this.growthEngine = growthEngine;
    this.leads = [];
    this.proposals = [];
    this.touches = [];
    this.payments = [];
    this.packages = [
      {
        id: "premium-rpc",
        name: "Premium RPC + Webhooks",
        segment: "wallets_developers",
        setupUsd: 0,
        monthlyUsd: 999,
        pilotUsd: 999,
        planId: "pro",
        included: ["premium RPC", "signed webhooks", "usage dashboard", "SDK support"],
        sla: "99.9% target uptime, shared pool, priority support",
        activation: ["developer KYB", "accepted API terms", "paid subscription or approved trial"]
      },
      {
        id: "dedicated-rpc-pool",
        name: "Dedicated RPC Pool",
        segment: "wallets_market_makers",
        setupUsd: 10000,
        monthlyUsd: 7500,
        pilotUsd: 5000,
        planId: "enterprise",
        included: ["dedicated chain pool", "rate-limit isolation", "SLA telemetry", "private escalation channel"],
        sla: "99.95% target uptime, dedicated capacity envelope",
        activation: ["enterprise order form", "network allowlist", "capacity profile", "security review"]
      },
      {
        id: "relay-webhook-intelligence",
        name: "Relay + Webhook Intelligence",
        segment: "trading_infra",
        setupUsd: 5000,
        monthlyUsd: 2500,
        pilotUsd: 2500,
        planId: "pro",
        included: ["MEV-safe relay routing", "webhook fanout", "wallet analytics", "anomaly alerts"],
        sla: "priority queue with measured latency and delivery evidence",
        activation: ["API key", "webhook destination verification", "relay consent policy"]
      },
      {
        id: "issuer-launch",
        name: "Issuer Launch Stack",
        segment: "token_issuers",
        setupUsd: 25000,
        monthlyUsd: 5000,
        pilotUsd: 7500,
        planId: "enterprise",
        included: ["token factory", "controlled RFQ listing", "proof pack", "issuer analytics", "compliance evidence export"],
        sla: "launch war-room, controlled liquidity limits, audit event export",
        activation: ["issuer KYB", "token classification", "legal disclosures", "risk limits approved"]
      },
      {
        id: "white-label-exchange",
        name: "White-Label Exchange Infrastructure",
        segment: "fintechs_brokers",
        setupUsd: 75000,
        monthlyUsd: 25000,
        pilotUsd: 15000,
        planId: "enterprise",
        included: ["ledger", "RFQ/trading APIs", "custody orchestration", "market surveillance", "admin control plane"],
        sla: "dedicated integration lane, private environments, executive escalation",
        activation: ["regulated-entity review", "data-processing addendum", "security review", "go-live checklist"]
      },
      {
        id: "managed-custody-orchestration",
        name: "Managed Custody Orchestration",
        segment: "institutions",
        setupUsd: 50000,
        monthlyUsd: 15000,
        pilotUsd: 10000,
        planId: "enterprise",
        included: ["policy engine", "MPC/HSM workflow integration", "proof-of-reserves", "withdrawal risk controls"],
        sla: "policy-controlled signing workflows with immutable audit trail",
        activation: ["custody entitlement", "signer ceremony", "withdrawal policy approval", "incident runbook"]
      }
    ];
    this.outboundSequences = buildOutboundSequences();
  }

  captureLead(input) {
    const lead = this.normalizeLead(input);
    this.leads.push(lead);
    if (this.growthEngine) {
      try {
        this.growthEngine.captureLead({
          email: lead.email,
          company: lead.company,
          name: lead.name,
          role: lead.role,
          segment: lead.segment,
          source: lead.source,
          jurisdiction: lead.jurisdiction,
          consent: true,
          budgetUsd: lead.budgetUsd,
          expectedMonthlyVolumeUsd: lead.expectedMonthlyVolumeUsd
        });
      } catch {
        // Growth capture is best-effort; enterprise lead capture remains the source for this funnel.
      }
    }
    this.eventBus.publish("EnterpriseLeadCaptured", lead);
    return lead;
  }

  createProposal({ leadId, leadSnapshot, packageId, expectedMonthlyUnits = 0, notes = "", requestedGoLiveDays = 14 } = {}) {
    let lead = this.leads.find((row) => row.id === leadId);
    if (!lead && leadSnapshot?.id === leadId) {
      lead = {
        ...leadSnapshot,
        replicaImportedAt: new Date().toISOString()
      };
      this.leads.push(lead);
    }
    if (!lead) throw new Error("Known enterprise lead required before proposal");
    const offer = this.package(packageId ?? lead.packageId);
    const monthlyUsage = Number(expectedMonthlyUnits || lead.expectedMonthlyUnits || 0);
    const overage = estimateOverage({ developerPlatform: this.developerPlatform, planId: offer.planId, monthlyUsage });
    const proposal = {
      id: `prop-${randomUUID()}`,
      leadId: lead.id,
      company: lead.company,
      packageId: offer.id,
      packageName: offer.name,
      status: "draft_ready",
      signatureStatus: "unsigned",
      paymentStatus: "unpaid",
      setupUsd: offer.setupUsd,
      pilotUsd: offer.pilotUsd,
      monthlyRecurringUsd: offer.monthlyUsd,
      estimatedUsageOverageUsd: overage,
      firstMonthDueUsd: round(offer.setupUsd + offer.monthlyUsd + overage),
      annualContractValueUsd: round((offer.monthlyUsd * 12) + offer.setupUsd),
      expectedMonthlyUnits: monthlyUsage,
      requestedGoLiveDays: Number(requestedGoLiveDays),
      sla: offer.sla,
      included: offer.included,
      activation: offer.activation,
      notes,
      revenueRecognition: "no_revenue_booked_until_external_payment_reference_is_reconciled",
      nextActions: [
        "Send proposal/order form to authorized signer.",
        "Collect KYB, security and entitlement evidence.",
        "Record payment reference only after verified bank/card/crypto receipt.",
        "Activate API subscription and capacity limits after reconciliation."
      ],
      createdAt: new Date().toISOString(),
      expiresAt: new Date(Date.now() + 7 * dayMs).toISOString()
    };
    this.proposals.push(proposal);
    this.eventBus.publish("EnterpriseProposalCreated", proposal);
    return proposal;
  }

  recordTouch({ leadId, channel, externalMessageId, subject, consentBasis = "explicit_consent", status = "sent" }) {
    const lead = this.leads.find((row) => row.id === leadId);
    if (!lead) throw new Error("leadId not found");
    if (!channel) throw new Error("channel required");
    const touch = {
      id: `touch-${randomUUID()}`,
      leadId,
      channel,
      externalMessageId,
      subject,
      consentBasis,
      status,
      createdAt: new Date().toISOString()
    };
    this.touches.push(touch);
    lead.lastTouchAt = touch.createdAt;
    lead.status = lead.score >= 85 ? "enterprise_sales_qualified_contacted" : lead.status;
    this.eventBus.publish("EnterpriseTouchRecorded", touch);
    return touch;
  }

  recordVerifiedPayment({ proposalId, amountUsd, asset = "USD", externalReference, rail = "invoice", reconciled = false }) {
    const proposal = this.proposals.find((row) => row.id === proposalId);
    if (!proposal) throw new Error("proposalId not found");
    if (!externalReference) throw new Error("external payment reference required");
    const payment = {
      id: `pay-${randomUUID()}`,
      proposalId,
      amountUsd: round(amountUsd),
      asset,
      externalReference,
      rail,
      reconciled: Boolean(reconciled),
      status: reconciled ? "reconciled" : "pending_reconciliation",
      createdAt: new Date().toISOString()
    };
    this.payments.push(payment);
    proposal.paymentStatus = payment.status;
    if (reconciled) proposal.status = "paid_ready_to_activate";
    this.eventBus.publish("EnterprisePaymentRecorded", payment);
    return payment;
  }

  forecast({ horizonHours = 72 } = {}) {
    const horizon = Number(horizonHours);
    const qualifiedLeads = this.leads.filter((lead) => lead.score >= 65).length;
    const proposals = this.proposals.length;
    const weightedPipelineMrrUsd = round(this.proposals.reduce((sum, proposal) => {
      const lead = this.leads.find((row) => row.id === proposal.leadId);
      const weight = lead?.score >= 85 ? 0.35 : lead?.score >= 65 ? 0.18 : 0.08;
      return sum + proposal.monthlyRecurringUsd * weight;
    }, 0));
    const verifiedPaymentsUsd = round(this.payments.filter((row) => row.reconciled).reduce((sum, row) => sum + row.amountUsd, 0));
    return {
      generatedAt: new Date().toISOString(),
      horizonHours: horizon,
      verifiedPaymentsUsd,
      verifiedMrrUsd: this.verifiedMrr(),
      qualifiedLeads,
      proposals,
      weightedPipelineMrrUsd,
      conservative: {
        expectedPaidPilots: qualifiedLeads >= 3 ? 1 : 0,
        expectedCashUsd: qualifiedLeads >= 3 ? 2500 : 0,
        expectedMrrUsd: qualifiedLeads >= 3 ? 999 : 0
      },
      base: {
        expectedPaidPilots: Math.min(3, Math.floor(qualifiedLeads / 2)),
        expectedCashUsd: Math.min(3, Math.floor(qualifiedLeads / 2)) * 5000,
        expectedMrrUsd: Math.min(3, Math.floor(qualifiedLeads / 2)) * 2500
      },
      upside: {
        expectedHighTicketDeals: proposals >= 2 ? 1 : 0,
        expectedCashUsd: proposals >= 2 ? 25000 : 0,
        expectedMrrUsd: proposals >= 2 ? 7500 : 0
      },
      caveat: "Forecast only. Revenue is counted as generated only after payment reference and reconciliation."
    };
  }

  summary() {
    const proposalMrr = round(this.proposals.reduce((sum, row) => sum + row.monthlyRecurringUsd, 0));
    return {
      generatedAt: new Date().toISOString(),
      packageCount: this.packages.length,
      leadCount: this.leads.length,
      contactedLeadCount: new Set(this.touches.map((row) => row.leadId)).size,
      proposalCount: this.proposals.length,
      proposalPipelineMrrUsd: proposalMrr,
      verifiedPaymentsUsd: round(this.payments.filter((row) => row.reconciled).reduce((sum, row) => sum + row.amountUsd, 0)),
      verifiedMrrUsd: this.verifiedMrr(),
      byStatus: countBy(this.leads, "status"),
      bySegment: countBy(this.leads, "segment"),
      packages: this.packages,
      forecast72h: this.forecast({ horizonHours: 72 }),
      operatingRules: [
        "No fake users, fake usage, fake volume or artificial revenue.",
        "No client is marked contacted unless a real outbound touch is recorded with a channel reference.",
        "No revenue is recognized unless a real external payment reference is captured and reconciled.",
        "Every enterprise activation remains subject to KYB, security, entitlement and legal review."
      ]
    };
  }

  package(packageId) {
    const offer = this.packages.find((row) => row.id === packageId);
    if (!offer) throw new Error(`Unknown enterprise package: ${packageId}`);
    return offer;
  }

  normalizeLead({ email, company, name, role, segment, packageId = "dedicated-rpc-pool", source = "enterprise_landing", jurisdiction = "EU", consent, budgetUsd = 0, expectedMonthlyVolumeUsd = 0, expectedMonthlyUnits = 0, urgency = "this_month" }) {
    if (!email || !String(email).includes("@")) throw new Error("Valid email required");
    if (!company) throw new Error("company required");
    if (!consent) throw new Error("Explicit consent required");
    const offer = this.package(packageId);
    const score = scoreLead({ role, segment: segment ?? offer.segment, budgetUsd, expectedMonthlyVolumeUsd, expectedMonthlyUnits, urgency, offer });
    return {
      id: `ent-${randomUUID()}`,
      email: String(email).toLowerCase(),
      company,
      name,
      role,
      segment: segment ?? offer.segment,
      packageId: offer.id,
      source,
      jurisdiction,
      consent: true,
      budgetUsd: Number(budgetUsd),
      expectedMonthlyVolumeUsd: Number(expectedMonthlyVolumeUsd),
      expectedMonthlyUnits: Number(expectedMonthlyUnits),
      urgency,
      score,
      status: score >= 85 ? "enterprise_sales_qualified" : score >= 65 ? "sales_qualified" : score >= 40 ? "technical_discovery" : "nurture",
      nextAction: score >= 85 ? "same_day_founder_demo" : score >= 65 ? "send_technical_proposal" : "route_to_nurture",
      createdAt: new Date().toISOString()
    };
  }

  verifiedMrr() {
    const reconciledProposalIds = new Set(this.payments.filter((row) => row.reconciled).map((row) => row.proposalId));
    return round(this.proposals
      .filter((proposal) => reconciledProposalIds.has(proposal.id))
      .reduce((sum, proposal) => sum + proposal.monthlyRecurringUsd, 0));
  }
}

function estimateOverage({ developerPlatform, planId, monthlyUsage }) {
  if (!developerPlatform || !monthlyUsage) return 0;
  const plan = developerPlatform.plan(planId);
  const overageUnits = Math.max(0, Number(monthlyUsage) - plan.includedUnits);
  return round(overageUnits / 1_000_000 * plan.overageUsdPerMillion);
}

function scoreLead({ role, segment, budgetUsd, expectedMonthlyVolumeUsd, expectedMonthlyUnits, urgency, offer }) {
  let score = 20;
  if (/founder|ceo|cto|head|vp|director|partner/i.test(role ?? "")) score += 18;
  if (["token_issuers", "fintechs_brokers", "wallets_market_makers", "trading_infra", "institutions"].includes(segment)) score += 14;
  if (Number(budgetUsd) >= offer.pilotUsd) score += 18;
  if (Number(budgetUsd) >= offer.setupUsd + offer.monthlyUsd) score += 12;
  if (Number(expectedMonthlyVolumeUsd) >= 1_000_000) score += 12;
  if (Number(expectedMonthlyUnits) >= 10_000_000) score += 10;
  if (urgency === "24h" || urgency === "this_week") score += 16;
  return Math.min(100, score);
}

function buildOutboundSequences() {
  return [
    {
      id: "issuer-founder-24h",
      segment: "token_issuers",
      channel: "email_linkedin",
      subject: "Controlled token launch stack with RFQ liquidity and proof exports",
      steps: [
        "Day 0: founder note with launch-risk audit angle and same-day diligence CTA.",
        "Day 1: technical proof pack: token factory, RFQ lifecycle, proof-of-reserves/liabilities.",
        "Day 3: offer paid issuer launch pilot with fixed activation checklist."
      ]
    },
    {
      id: "wallet-rpc-pool",
      segment: "wallet_providers",
      channel: "email_partner_intro",
      subject: "Dedicated RPC + relay pool with wallet analytics",
      steps: [
        "Day 0: latency/cost framing and 7-day paid pilot offer.",
        "Day 1: Postman quickstart and webhook delivery evidence.",
        "Day 4: SLA and dedicated pool proposal."
      ]
    },
    {
      id: "fintech-white-label",
      segment: "fintechs_brokers",
      channel: "founder_direct",
      subject: "White-label exchange, ledger and RFQ infrastructure",
      steps: [
        "Day 0: executive one-pager and compliance-ready architecture claim.",
        "Day 2: integration map covering ledger, RFQ, custody orchestration and admin plane.",
        "Day 5: paid discovery workshop and order form."
      ]
    }
  ];
}

function countBy(rows, field) {
  return rows.reduce((acc, row) => {
    const key = row[field] ?? "unknown";
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
}

function round(value) {
  return Math.round((Number(value) + Number.EPSILON) * 1e8) / 1e8;
}

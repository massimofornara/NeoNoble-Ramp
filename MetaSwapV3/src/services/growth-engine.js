import { randomUUID } from "node:crypto";

export class GrowthEngine {
  constructor({ revenueEngine, eventBus }) {
    this.revenueEngine = revenueEngine;
    this.eventBus = eventBus;
    this.leads = [];
    this.referrals = [];
    this.campaigns = [
      {
        id: "issuer-abm",
        name: "Issuer ABM Sprint",
        segment: "token_issuers",
        channel: "linkedin_email_events",
        dailyTarget: 150,
        positioning: "Launch a controlled token market with RFQ liquidity, custody, compliance evidence and fiat settlement.",
        cta: "Book issuer launch assessment",
        complianceGate: "KYB and token classification before any listing."
      },
      {
        id: "liquidity-partner",
        name: "Liquidity Partner Blitz",
        segment: "market_makers_otc",
        channel: "direct_partnerships",
        dailyTarget: 40,
        positioning: "Plug into custom-token RFQ flow, balance-sheet limits and surveillance-ready settlement.",
        cta: "Request RFQ integration docs",
        complianceGate: "Counterparty KYB, credit line and SLA review."
      },
      {
        id: "enterprise-api",
        name: "Enterprise API Pipeline",
        segment: "brokers_fintechs",
        channel: "partner_sales",
        dailyTarget: 60,
        positioning: "Embed tokenization, wallet auth, ledger, proof and payout orchestration through one API.",
        cta: "Start technical diligence",
        complianceGate: "Product entitlement by jurisdiction."
      },
      {
        id: "builder-referral",
        name: "Builder Referral Loop",
        segment: "web3_builders",
        channel: "community_referral",
        dailyTarget: 250,
        positioning: "Deploy a real token and route it through a production-grade RFQ and treasury engine.",
        cta: "Join launch cohort",
        complianceGate: "No investment return claims; utility and risk disclosure required."
      }
    ];
  }

  captureLead({ email, company, name, role, segment = "token_issuers", source = "landing", jurisdiction = "EU", consent, budgetUsd = 0, expectedMonthlyVolumeUsd = 0 }) {
    if (!email || !String(email).includes("@")) throw new Error("Valid email required");
    if (!consent) throw new Error("Explicit marketing consent is required");
    const campaign = this.bestCampaign(segment);
    const score = this.scoreLead({ company, role, segment, budgetUsd, expectedMonthlyVolumeUsd, jurisdiction });
    const lead = {
      id: randomUUID(),
      email: String(email).toLowerCase(),
      company,
      name,
      role,
      segment,
      source,
      jurisdiction,
      consent: true,
      budgetUsd: Number(budgetUsd),
      expectedMonthlyVolumeUsd: Number(expectedMonthlyVolumeUsd),
      score,
      status: score >= 75 ? "sales_qualified" : score >= 45 ? "marketing_qualified" : "nurture",
      campaignId: campaign.id,
      nextAction: score >= 75 ? "founder_sales_call" : "automated_compliance_safe_nurture",
      createdAt: new Date().toISOString()
    };
    this.leads.push(lead);
    this.eventBus.publish("GrowthLeadCaptured", lead);
    return lead;
  }

  recordReferral({ referrerId, referredEmail, segment = "web3_builders", consent }) {
    if (!consent) throw new Error("Referral contact consent is required");
    if (!referredEmail || !String(referredEmail).includes("@")) throw new Error("Valid referred email required");
    const referral = {
      id: randomUUID(),
      referrerId,
      referredEmail: String(referredEmail).toLowerCase(),
      segment,
      status: "captured",
      rewardStatus: "pending_compliant_activation",
      createdAt: new Date().toISOString()
    };
    this.referrals.push(referral);
    this.eventBus.publish("GrowthReferralCaptured", referral);
    return referral;
  }

  summary() {
    const target = this.revenueEngine.summary({ targetMonthlyUsd: 10_000_000 });
    const byStatus = this.countBy(this.leads, "status");
    const bySegment = this.countBy(this.leads, "segment");
    const qualified = (byStatus.sales_qualified ?? 0) + (byStatus.marketing_qualified ?? 0);
    return {
      generatedAt: new Date().toISOString(),
      leadCount: this.leads.length,
      qualifiedLeadCount: qualified,
      referralCount: this.referrals.length,
      byStatus,
      bySegment,
      campaigns: this.campaigns,
      revenueTarget: target.requiredMonthlyVolume,
      aggressiveButCompliantRules: [
        "No guaranteed return or profit claims.",
        "No unsolicited bulk messaging.",
        "Consent-based outreach only.",
        "Jurisdiction and entitlement checks before product activation.",
        "Issuer claims must match token legal classification and disclosures."
      ],
      fastestPath: [
        "Founder-led ABM to issuers and fintech brokers.",
        "Paid proof/custody/compliance packages for issuers.",
        "RFQ and market-making packages with real SLAs.",
        "Enterprise API/FIX integrations with setup fees.",
        "Referral loop for builders after risk disclosure."
      ]
    };
  }

  bestCampaign(segment) {
    return this.campaigns.find((campaign) => campaign.segment === segment) ?? this.campaigns[0];
  }

  scoreLead({ company, role, segment, budgetUsd, expectedMonthlyVolumeUsd, jurisdiction }) {
    let score = 20;
    if (company) score += 10;
    if (role && /founder|ceo|cto|head|director|partner/i.test(role)) score += 15;
    if (["token_issuers", "brokers_fintechs", "market_makers_otc"].includes(segment)) score += 20;
    if (Number(budgetUsd) >= 25_000) score += 15;
    if (Number(expectedMonthlyVolumeUsd) >= 1_000_000) score += 20;
    if (["EU", "UK", "ROW"].includes(jurisdiction)) score += 5;
    return Math.min(100, score);
  }

  countBy(rows, field) {
    return rows.reduce((acc, row) => {
      const key = row[field] ?? "unknown";
      acc[key] = (acc[key] ?? 0) + 1;
      return acc;
    }, {});
  }
}

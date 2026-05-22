const tierRank = { none: 0, basic: 1, enhanced: 2, institutional: 3 };

export class ComplianceHub {
  constructor(eventBus) {
    this.eventBus = eventBus;
    this.users = new Map();
    this.cases = [];
  }

  upsertUser(user) {
    const normalized = {
      status: "active",
      kycTier: "basic",
      jurisdiction: "EU",
      sanctionsClear: true,
      pep: false,
      fraudScore: 0.05,
      clusterId: user.id,
      ...user
    };
    this.users.set(normalized.id, normalized);
    this.eventBus.publish("UserComplianceUpdated", { userId: normalized.id, kycTier: normalized.kycTier });
    return normalized;
  }

  getUser(userId) {
    const user = this.users.get(userId);
    if (!user) throw new Error(`Unknown user ${userId}`);
    return user;
  }

  tierAllows(userTier, requiredTier) {
    return (tierRank[userTier] ?? 0) >= (tierRank[requiredTier] ?? 0);
  }

  screenUser(user, asset) {
    const reasons = [];
    if (user.status !== "active") reasons.push("USER_NOT_ACTIVE");
    if (!user.sanctionsClear) reasons.push("SANCTIONS_HIT");
    if (user.pep && asset.riskTier === "high") reasons.push("PEP_HIGH_RISK_ASSET");
    if (!this.tierAllows(user.kycTier, asset.requiredTier)) reasons.push("KYC_TIER_TOO_LOW");
    if (!asset.allowedJurisdictions.includes(user.jurisdiction)) reasons.push("JURISDICTION_BLOCKED");
    return { allowed: reasons.length === 0, reasons };
  }

  scoreAml({ user, amountUsd, rail = "crypto", counterpartyRisk = 0 }) {
    let score = user.fraudScore + counterpartyRisk;
    if (amountUsd > 10000) score += 0.1;
    if (amountUsd > 100000) score += 0.25;
    if (rail === "card") score += 0.08;
    return Math.min(1, Number(score.toFixed(4)));
  }

  openCase(type, subjectId, reason, severity = "medium") {
    const complianceCase = { id: `case-${this.cases.length + 1}`, type, subjectId, reason, severity, status: "open", createdAt: new Date().toISOString() };
    this.cases.push(complianceCase);
    this.eventBus.publish("ComplianceCaseOpened", complianceCase);
    return complianceCase;
  }
}

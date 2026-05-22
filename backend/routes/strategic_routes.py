"""
Strategic Operations API — 0 → IPO roadmap, Virtual→Real reconciliation, Payout Guard.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from routes.auth import get_current_user
from services.virtual_real_engine import VirtualRealEngine

router = APIRouter(prefix="/strategic", tags=["Strategic Operations"])


@router.get("/real-treasury")
async def real_treasury(current_user: dict = Depends(get_current_user)):
    """Real treasury: ONLY proven on-chain + settled fiat balances."""
    engine = VirtualRealEngine.get_instance()
    return await engine.get_real_treasury()


@router.get("/virtual-metrics")
async def virtual_metrics(current_user: dict = Depends(get_current_user)):
    """Virtual demand metrics: NOT real money. For forecasting only."""
    engine = VirtualRealEngine.get_instance()
    return await engine.get_virtual_metrics()


@router.get("/reconciliation")
async def reconciliation(current_user: dict = Depends(get_current_user)):
    """Full reconciliation: real treasury vs virtual demand."""
    engine = VirtualRealEngine.get_instance()
    return await engine.reconcile()


@router.get("/payout-guard/{asset}")
async def payout_guard(asset: str, amount: float = 1.0, current_user: dict = Depends(get_current_user)):
    """Check if real payout can be executed for given asset/amount."""
    engine = VirtualRealEngine.get_instance()
    return await engine.can_payout(asset, amount)


@router.get("/ipo-roadmap")
async def ipo_roadmap(current_user: dict = Depends(get_current_user)):
    """Complete 0 → IPO roadmap with phases, capital, partners, KPIs."""
    return {
        "title": "NeoNoble Ramp — Piano Strategico 0 → IPO",
        "phases": [
            {
                "id": 1, "name": "Foundation (0-30 giorni)",
                "objectives": [
                    "Stabilizzazione produzione e infrastruttura",
                    "Treasury reale operativa (hot wallet funded)",
                    "Primo payout reale (crypto + fiat) verificato end-to-end",
                    "Revenue engine attivo: fee reali da trade reali",
                ],
                "deliverables": [
                    "Sistema in produzione con execution reale",
                    "3+ tx hash reali verificati su BscScan",
                    "Primo payout Stripe SEPA completato",
                    "Admin dashboard con real vs virtual chiaramente separati",
                ],
                "capital_min_eur": 25000,
                "capital_recommended_eur": 75000,
                "capital_breakdown": {
                    "treasury_liquidity": 15000,
                    "infrastructure": 3000,
                    "legal_basic": 5000,
                    "operational": 2000,
                },
                "kpis": ["10+ trade reali/giorno", "EUR 1,000+ volume reale/giorno", "0 payout bloccati per fondi insufficienti"],
                "risks": ["Liquidita hot wallet insufficiente", "Volatilita gas BSC"],
                "milestone_next": "Revenue reale > EUR 100/mese da fee",
            },
            {
                "id": 2, "name": "Traction (30-90 giorni)",
                "objectives": [
                    "KYC/AML provider integrato (Onfido o Sumsub)",
                    "Circle USDC rails attivi",
                    "50+ utenti attivi",
                    "Revenue reale consistente",
                ],
                "deliverables": [
                    "KYC automatizzato per onboarding",
                    "EUR/USDC conversione automatica",
                    "LP tier-1 attivo (almeno 1 provider)",
                    "Compliance monitoring attivo",
                ],
                "capital_min_eur": 100000,
                "capital_recommended_eur": 250000,
                "capital_breakdown": {
                    "treasury_liquidity": 50000,
                    "kyc_aml_provider": 15000,
                    "circle_integration": 10000,
                    "legal_compliance": 15000,
                    "team_2_people": 10000,
                },
                "kpis": ["100+ trade/giorno", "EUR 50,000+ volume/giorno", "95%+ KYC pass rate", "0 compliance violations"],
                "risks": ["KYC provider rejection rate", "Circle onboarding delays"],
                "milestone_next": "EUR 10,000+ revenue/mese + KYC attivo",
            },
            {
                "id": 3, "name": "Growth (3-6 mesi)",
                "objectives": [
                    "EMI license application submitted",
                    "Banking partner attivo (IBAN issuance)",
                    "Card issuing pilot",
                    "Institutional LP onboarding",
                ],
                "deliverables": [
                    "Application EMI depositata presso regolatore",
                    "IBAN reali emessi per utenti",
                    "Carta prepagata Visa/MC pilota",
                    "3+ LP tier-1 attivi",
                    "IFRS-ready accounting system",
                ],
                "capital_min_eur": 500000,
                "capital_recommended_eur": 1500000,
                "capital_breakdown": {
                    "treasury_liquidity": 200000,
                    "emi_application": 100000,
                    "banking_partner": 50000,
                    "card_issuing_pilot": 50000,
                    "team_5_people": 50000,
                    "audit_ifrs": 30000,
                    "legal": 20000,
                },
                "kpis": ["1000+ utenti", "EUR 500,000+ volume/giorno", "EMI application filed", "3+ LP attivi"],
                "risks": ["EMI rejection/delays", "Banking partner due diligence", "Regulatory changes"],
                "milestone_next": "EMI application accepted + EUR 100K revenue/mese",
            },
            {
                "id": 4, "name": "Scale (6-12 mesi)",
                "objectives": [
                    "EMI license obtained",
                    "Multi-country operations (EU)",
                    "CASP (MiCA) registration",
                    "Series A fundraising",
                    "TARGET2/SEPA Instant access",
                ],
                "deliverables": [
                    "EMI license attiva",
                    "Operations in 5+ paesi EU",
                    "CASP registration completata",
                    "Series A closed (EUR 3-10M)",
                    "SWIFT integration",
                    "Board strutturato con independent directors",
                ],
                "capital_min_eur": 3000000,
                "capital_recommended_eur": 10000000,
                "capital_breakdown": {
                    "treasury_liquidity": 1000000,
                    "compliance_ongoing": 200000,
                    "team_15_people": 300000,
                    "banking_infrastructure": 200000,
                    "marketing_expansion": 300000,
                    "legal_multi_jurisdiction": 200000,
                    "technology_scaling": 150000,
                    "audit_big4": 150000,
                    "reserve_safeguarding": 500000,
                },
                "kpis": ["10,000+ utenti", "EUR 5M+ volume/giorno", "EMI license active", "Series A closed"],
                "risks": ["Fundraising market conditions", "Regulatory enforcement", "Competition"],
                "milestone_next": "EUR 1M+ revenue/anno + EMI active + Series A",
            },
            {
                "id": 5, "name": "IPO Readiness (12-24 mesi)",
                "objectives": [
                    "Pre-IPO round (Series B)",
                    "Governance completa",
                    "3 anni di bilanci auditati (proiezione)",
                    "Listing preparation",
                ],
                "deliverables": [
                    "NeoNoble Holding AG quotabile",
                    "3 subsidiaries operative",
                    "Board con 2+ independent directors",
                    "Big 4 audit engagement",
                    "IFRS-compliant financial reporting",
                    "Investment bank mandate per IPO",
                    "Roadshow materials",
                ],
                "capital_min_eur": 15000000,
                "capital_recommended_eur": 50000000,
                "capital_breakdown": {
                    "treasury_institutional": 5000000,
                    "team_50_people": 2000000,
                    "compliance_multi_license": 1000000,
                    "technology_enterprise": 1000000,
                    "marketing_brand": 1000000,
                    "legal_ipo_preparation": 2000000,
                    "audit_3_years": 500000,
                    "investment_bank_fees": 2500000,
                    "safeguarding_reserve": 5000000,
                },
                "kpis": ["100,000+ utenti", "EUR 50M+ volume/giorno", "EUR 10M+ revenue/anno", "Pre-IPO valuation EUR 100M+"],
                "risks": ["Market downturn", "Regulatory changes", "IPO window timing"],
                "milestone_next": "IPO or strategic acquisition",
            },
        ],
        "capital_summary": {
            "phase_1_min": 25000, "phase_1_rec": 75000,
            "phase_2_min": 100000, "phase_2_rec": 250000,
            "phase_3_min": 500000, "phase_3_rec": 1500000,
            "phase_4_min": 3000000, "phase_4_rec": 10000000,
            "phase_5_min": 15000000, "phase_5_rec": 50000000,
            "total_min": 18625000,
            "total_recommended": 61825000,
        },
        "partner_matrix": {
            "banking_iban_sepa": {
                "purpose": "IBAN issuance, SEPA transfers",
                "phase": 2,
                "primary": ["Banking Circle", "ClearBank", "Modulr"],
                "fallback": ["Stripe Treasury", "Swan"],
                "dependencies": ["EMI license or sponsor bank"],
            },
            "card_issuing": {
                "purpose": "Visa/Mastercard debit/prepaid cards",
                "phase": 3,
                "primary": ["Marqeta", "Enfuce", "Moorwand"],
                "fallback": ["Transact Payments", "i2c"],
                "dependencies": ["EMI license", "BIN sponsor"],
            },
            "kyc_aml": {
                "purpose": "Identity verification, AML screening",
                "phase": 2,
                "primary": ["Sumsub", "Onfido"],
                "fallback": ["Jumio", "Veriff"],
                "dependencies": ["None (SaaS)"],
            },
            "on_off_ramp": {
                "purpose": "Fiat ↔ crypto conversion",
                "phase": 1,
                "primary": ["Stripe (SEPA)", "Circle (USDC)"],
                "fallback": ["MoonPay", "Transak"],
                "dependencies": ["Stripe active (done)", "Circle API key"],
            },
            "stablecoin_rail": {
                "purpose": "USDC/USDT rails for settlement",
                "phase": 2,
                "primary": ["Circle", "Paxos"],
                "fallback": ["Tether direct"],
                "dependencies": ["Circle API approval"],
            },
            "liquidity_provider": {
                "purpose": "Institutional market making, order flow",
                "phase": 3,
                "primary": ["Wintermute", "GSR", "Jump Crypto"],
                "fallback": ["Keyrock", "CMS Holdings"],
                "dependencies": ["Volume traction", "API docs"],
            },
            "audit_accounting": {
                "purpose": "IFRS audit, financial reporting",
                "phase": 3,
                "primary": ["Deloitte", "PwC"],
                "fallback": ["Grant Thornton", "BDO"],
                "dependencies": ["Revenue history", "Clean books"],
            },
            "legal_regulatory": {
                "purpose": "EMI/CASP licensing, corporate structure",
                "phase": 2,
                "primary": ["Hogan Lovells", "Clifford Chance"],
                "fallback": ["CMS", "Bird & Bird"],
                "dependencies": ["Budget allocation"],
            },
        },
        "conversion_model": {
            "principle": "virtual demand → real trades → fee/spread reali → treasury reale → payout reale",
            "rules": [
                "I valori virtuali (ledger credits, simulated volume, test trades) NON sono denaro reale",
                "Nessun accredito su conto o wallet senza proof verificabile (tx_hash, payout_id, bank confirmation)",
                "Revenue = SOLO fee + spread da operazioni con proof reale",
                "Treasury = SOLO saldi verificati on-chain (RPC) + payout settled (Stripe)",
                "Ogni payout richiede payout_guard check prima dell'esecuzione",
            ],
            "api_endpoints": {
                "real_treasury": "GET /api/strategic/real-treasury",
                "virtual_metrics": "GET /api/strategic/virtual-metrics",
                "reconciliation": "GET /api/strategic/reconciliation",
                "payout_guard": "GET /api/strategic/payout-guard/{asset}?amount=X",
            },
        },
    }

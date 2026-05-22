# NeoNoble Ramp — Piano Strategico 0 → IPO

## Executive Summary

NeoNoble Ramp è un'infrastruttura fintech/exchange che opera con execution reale on-chain (BSC Mainnet), payout fiat reale (Stripe SEPA), e treasury verificabile. Il sistema è progettato per scalare da startup crypto-native a EMI licenziata quotabile, con struttura holding (NeoNoble Holding AG) e subsidiaries operative.

**Stato attuale reale:**
- 3 transazioni on-chain reali verificate su BscScan
- Hot wallet: 0x18CE1930820d5e1B87F37a8a2F7Cf59E7BF6da4E
- Treasury reale: ~396.99 NENO + 0.00483 BNB on-chain
- Stripe SEPA live (sk_live) per payout fiat a IBAN IT22B...
- 12 engine operativi (matching, risk, clearing, profit, compliance, capital markets)

---

## Gap Analysis

| Area | Stato | Gap |
|------|-------|-----|
| Execution on-chain | ATTIVO (NENO, BNB) | WETH/BTCB non funded nel hot wallet |
| Payout fiat | ATTIVO (Stripe SEPA) | NIUM bloccato su templateId |
| KYC/AML | Framework pronto | Nessun provider reale integrato |
| EMI License | Struttura pronta | Application non depositata |
| Utenti reali | 1 (admin/owner) | Nessun utente esterno |
| Revenue reale | Fee da 3 trade reali | Volume insufficiente per sostenibilità |
| Liquidity | Solo treasury interno | Nessun LP esterno |
| Circle USDC | Non integrato | Richiede API key |
| Card issuing | Framework pronto | Richiede BIN sponsor + EMI |

---

## Timeline 0 → IPO

### Fase 1: Foundation (0-30 giorni)
**Obiettivi:** Stabilizzazione produzione, treasury funded, primi trade reali, revenue engine attivo.

| Task | Tipo | Output |
|------|------|--------|
| Depositare BNB + NENO nel hot wallet | Operativo | Treasury liquida |
| Depositare WETH + BTCB nel hot wallet | Operativo | ETH/BTC payout abilitati |
| Configurare Circle USDC API | Tecnico | EUR↔USDC rail |
| Pubblicare piattaforma su dominio proprio | Tecnico | Accessibilità pubblica |
| Primi 10 trade reali con utenti | Commerciale | Revenue reale |
| Verifica end-to-end: trade → fee → treasury → payout | QA | Pipeline completa |

**Capitale minimo:** EUR 25,000 | **Consigliato:** EUR 75,000
**KPI:** 10+ trade/giorno, EUR 1,000+ volume/giorno, EUR 100+ fee/mese
**Milestone:** Revenue reale > EUR 100/mese

### Fase 2: Traction (30-90 giorni)
**Obiettivi:** KYC provider, Circle, 50+ utenti, compliance operativa.

| Task | Tipo | Output |
|------|------|--------|
| Integrare Sumsub/Onfido per KYC | Tecnico | Onboarding automatizzato |
| Integrare Circle USDC | Tecnico | Stablecoin rail attivo |
| Onboardare primo LP tier-1 | Commerciale | Liquidità istituzionale |
| Legal advisor per EMI | Legale | Preparazione application |
| AML screening attivo | Compliance | Transaction monitoring |
| Privacy policy + T&C | Legale | Conformità GDPR |

**Capitale minimo:** EUR 100,000 | **Consigliato:** EUR 250,000
**KPI:** 50+ utenti, EUR 50K+ volume/giorno, 95% KYC pass rate
**Milestone:** EUR 10,000 revenue/mese + KYC attivo

### Fase 3: Growth (3-6 mesi)
**Obiettivi:** EMI application, banking partner, card pilot, IFRS.

| Task | Tipo | Output |
|------|------|--------|
| Depositare EMI application | Legale/Regolatorio | Application filed |
| Banking Circle/ClearBank onboarding | Operativo | IBAN issuance |
| Marqeta/Enfuce card pilot | Operativo | Carta prepagata |
| IFRS accounting setup | Finance | Bilanci standardizzati |
| 3+ LP tier-1 attivi | Commerciale | Profondità liquidità |
| SEPA Instant via RT1 | Tecnico | Settlement 10 secondi |

**Capitale minimo:** EUR 500,000 | **Consigliato:** EUR 1,500,000
**KPI:** 1,000+ utenti, EUR 500K+ volume/giorno, EMI filed
**Milestone:** EMI accepted + EUR 100K revenue/mese

### Fase 4: Scale (6-12 mesi)
**Obiettivi:** EMI license, multi-country, Series A, SWIFT.

| Task | Tipo | Output |
|------|------|--------|
| Ottenere EMI license | Regolatorio | License attiva |
| CASP registration (MiCA) | Regolatorio | Crypto asset compliance |
| Espansione in 5+ paesi EU | Commerciale | Multi-market |
| Series A fundraising | Finance | EUR 3-10M raised |
| Board strutturato | Governance | Independent directors |
| SWIFT gpi integration | Tecnico | Global transfers |
| TARGET2 application | Regolatorio/Banking | RTGS access |

**Capitale minimo:** EUR 3,000,000 | **Consigliato:** EUR 10,000,000
**KPI:** 10,000+ utenti, EUR 5M+ volume/giorno, EMI active, Series A closed
**Milestone:** EUR 1M+ revenue/anno + EMI + Series A

### Fase 5: IPO Readiness (12-24 mesi)
**Obiettivi:** Pre-IPO round, governance completa, 3 anni bilanci, listing.

| Task | Tipo | Output |
|------|------|--------|
| Pre-IPO (Series B) | Finance | EUR 15-50M raised |
| Big 4 audit engagement | Finance | Bilanci auditati |
| IFRS 3-year projections | Finance | Financial track record |
| Investment bank mandate | Finance | IPO preparation |
| Roadshow materials | Marketing/IR | Investor deck completo |
| Listing application | Legale | SIX/Euronext/LSE |

**Capitale minimo:** EUR 15,000,000 | **Consigliato:** EUR 50,000,000

---

## Capital Plan

| Fase | Minimo | Consigliato | Istituzionale |
|------|--------|-------------|---------------|
| 1. Foundation | EUR 25K | EUR 75K | — |
| 2. Traction | EUR 100K | EUR 250K | — |
| 3. Growth | EUR 500K | EUR 1.5M | EUR 3M |
| 4. Scale | EUR 3M | EUR 10M | EUR 20M |
| 5. IPO | EUR 15M | EUR 50M | EUR 100M+ |
| **Totale** | **EUR 18.6M** | **EUR 61.8M** | **EUR 123M+** |

---

## Partner Map

| Categoria | Primary | Fallback | Fase | Dipendenze |
|-----------|---------|----------|------|------------|
| Banking/IBAN/SEPA | Banking Circle, ClearBank | Modulr, Swan | 2-3 | EMI o sponsor |
| Card Issuing | Marqeta, Enfuce | Moorwand, i2c | 3 | EMI + BIN |
| KYC/AML | Sumsub, Onfido | Jumio, Veriff | 2 | SaaS (nessuna) |
| On/Off-ramp | Stripe (attivo), Circle | MoonPay, Transak | 1-2 | Circle API |
| Stablecoin | Circle (USDC) | Paxos | 2 | Circle approval |
| Liquidity | Wintermute, GSR | Jump, Keyrock | 3-4 | Volume traction |
| Audit | Deloitte, PwC | Grant Thornton | 3-4 | Revenue history |
| Legal | Hogan Lovells | Clifford Chance, CMS | 2+ | Budget |
| Exchange Routing | Binance, Kraken | Coinbase, OKX | 2-3 | API integrations |

---

## Regole Accredito Reale

1. **NESSUN accredito su conto o wallet senza proof reale**
2. **Fondi virtuali/ledger** = driver di domanda, forecasting, PnL simulato. MAI accreditabili.
3. **Payout guard** blocca automaticamente se fondi reali insufficienti nel hot wallet
4. **Ogni payout richiede:** tx_hash (crypto) OPPURE payout_id (fiat) OPPURE bank confirmation
5. **Stato "completed"** SOLO con proof verificabile. Altrimenti: pending_execution / pending_settlement / failed

### Endpoint di verifica:
- `GET /api/strategic/real-treasury` — solo saldi on-chain + fiat settled
- `GET /api/strategic/virtual-metrics` — metriche simulate (NON denaro)
- `GET /api/strategic/reconciliation` — real vs virtual
- `GET /api/strategic/payout-guard/{asset}?amount=X` — verifica disponibilità prima del payout

---

## Azioni Immediate (eseguibili ORA dalla piattaforma)

1. ✅ Execution reale NENO on-chain (3 tx verificati)
2. ✅ Payout guard attivo su tutti gli endpoint
3. ✅ Real vs Virtual dashboard separazione netta
4. ✅ Admin Command Center con PnL, treasury, compliance
5. ⏳ Depositare WETH/BTCB nel hot wallet per abilitare ETH/BTC reali
6. ⏳ Configurare Circle USDC API
7. ⏳ Configurare NIUM templateId dal portale
8. ⏳ Integrare KYC provider (Sumsub/Onfido)

---

## Critical Blockers Esterni

| Blocker | Azione richiesta | Da chi |
|---------|-----------------|--------|
| WETH/BTCB nel hot wallet | Deposito manuale da wallet esterno | Owner (Massimo) |
| Circle USDC API key | Registrazione su circle.com/developers | Owner |
| NIUM templateId | Configurazione portale NIUM | Owner |
| KYC provider | Account Sumsub/Onfido + API key | Owner |
| EMI application | Legal advisor + capital + business plan | Owner + Legale |
| Banking partner | Due diligence + sponsor bank | Owner + Partner |

Tutti gli altri componenti sono autonomamente operativi dalla piattaforma.

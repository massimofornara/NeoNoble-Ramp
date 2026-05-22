# MetaSwapV3 Revenue Scale Plan

Target: build toward USD 10,000,000 monthly net revenue. This is not guaranteed revenue; it is the operating model and instrumentation required to pursue it with real volume, real licenses, real liquidity and real bank/custody rails.

## Revenue Engine Now Wired

- Trading fees post to `platform:fees:<asset>`.
- RFQ/custom-token trades use a higher transparent fee schedule because they consume balance-sheet risk.
- Fiat payouts capture a fee only after the rail instruction is accepted.
- `/revenue/summary?targetMonthlyUsd=10000000` reports captured revenue, fee balances, target gap and required volume.

## Unit Economics

At 55 bps blended net take rate:

- Monthly volume required for USD 10M revenue: about USD 1.818B.
- Daily volume required: about USD 60.6M.

At 100 bps blended net take rate:

- Monthly volume required: USD 1.0B.
- Daily volume required: USD 33.3M.

At 25 bps blended net take rate:

- Monthly volume required: USD 4.0B.
- Daily volume required: USD 133.3M.

## Fastest Viable Path

1. B2B issuer pipeline, not retail-first.
   Close 50 to 100 token issuers paying launch, compliance, market-making and custody setup fees.

2. RFQ liquidity packages.
   Sell monthly issuer packages for controlled liquidity, quote support, surveillance and treasury reporting.

3. Payment and payout monetization.
   Charge payout, FX and treasury spread only where licensed and disclosed.

4. Enterprise API/FIX access.
   Paid market-maker, broker and issuer API tiers.

5. Custody and proof services.
   Charge custody, proof-of-reserves reporting and compliance evidence automation.

## 90-Day Operating Targets

- Month 1: 10 anchor issuers, USD 5M to 10M daily volume, USD 250k to 750k monthly revenue.
- Month 2: 30 issuers, USD 20M to 35M daily volume, USD 2M to 5M monthly revenue.
- Month 3: 60+ issuers, USD 60M+ daily volume, USD 10M monthly revenue run-rate if retention, liquidity and conversion hold.

## Hard Gates

- No revenue recognition from internal ledger-only activity.
- No payout revenue unless external rail confirms acceptance.
- No crypto settlement revenue unless on-chain custody can broadcast and reconcile.
- No token liquidity program without issuer KYB, asset classification and market abuse monitoring.

## Execution Priorities

- Fund real custody wallets and bank balances.
- Sign active market-maker and OTC counterparties with enforceable SLAs.
- Convert Token Factory into issuer onboarding funnel.
- Build issuer dashboard around liquidity, holders, compliance evidence and RFQ quality.
- Push high-margin B2B contracts before broad consumer spend.

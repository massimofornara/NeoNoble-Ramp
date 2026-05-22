# MetaSwapV3 Enterprise Revenue Activation

This playbook activates real B2B revenue without fake usage, fake clients, fake volume or artificial payments. Revenue is recognized only after a real payment reference is reconciled.

## 1 Hour

- Verify production health: `GET /health`, `GET /metrics`, `GET /enterprise/summary`.
- Open `GET /enterprise` and validate lead capture creates a scored lead plus draft proposal.
- Send only consent-based or warm outbound using the templates from `GET /enterprise/outbound-assets`.
- Prioritize five buyer categories: wallet providers, market makers, token issuers, Web3 agencies and regulated fintechs.
- Offer paid pilots only: premium RPC, dedicated RPC pool, relay/webhooks, issuer launch stack or white-label exchange infrastructure.

## 24 Hours

- Target 10 enterprise demos from warm networks, partner intros and consented inbound.
- Convert 3-5 paid pilots with invoice/payment reference before activation.
- For each paid pilot, record payment with `POST /enterprise/payments` only after external payment evidence exists.
- Activate API keys/subscriptions with `/developer/api-keys` and `/developer/subscriptions`.
- Monitor `metaswap_enterprise_leads`, `metaswap_enterprise_proposals`, `metaswap_enterprise_verified_mrr_usd`, RPC units and webhook queue.

## 7 Days

- Convert one high-ticket contract: issuer launch, dedicated RPC pool, or white-label exchange.
- Publish technical proof artifacts: OpenAPI, Postman kit, SDK examples, SLA telemetry screenshot, proof-of-reserves/liabilities snapshot.
- Add customer-specific rate limits, webhook destinations, chain pools and escalation contacts.
- Build partner channels with Web3 agencies, token legal advisors, auditors and wallet integrators.

## High-Ticket Offers

| Package | Setup | Monthly | Pilot | Best buyer |
| --- | ---: | ---: | ---: | --- |
| Premium RPC + Webhooks | $0 | $999 | $999 | Web3 startups |
| Dedicated RPC Pool | $10,000 | $7,500 | $5,000 | Wallets, MM desks |
| Relay + Webhook Intelligence | $5,000 | $2,500 | $2,500 | Trading infra teams |
| Issuer Launch Stack | $25,000 | $5,000 | $7,500 | Token issuers |
| White-Label Exchange Infrastructure | $75,000 | $25,000 | $15,000 | Fintechs, brokers |
| Managed Custody Orchestration | $50,000 | $15,000 | $10,000 | Institutions |

## Outbound Rules

- No guaranteed profit, return or liquidity claims.
- No unsolicited bulk messaging or scraped personal data.
- Use warm intros, consented lists, inbound forms and partner channels.
- Do not mark a lead contacted unless a real touch is recorded with `POST /enterprise/touches`.
- Do not mark MRR generated unless a reconciled payment exists.

## Founder Email

Subject: Dedicated RPC, relay and exchange infrastructure pilot

Hi {{first_name}},

MetaSwapV3 is a self-hosted exchange and Web3 infrastructure stack for teams that need dedicated RPC capacity, relay routing, signed webhooks, wallet analytics, RFQ/trading APIs and audit-ready proof exports.

We are opening a small number of paid infrastructure pilots this week. The fastest path is a scoped pilot: dedicated capacity, metered usage, SLA telemetry and a fixed integration checklist.

Worth a 20-minute technical screen today?

## LinkedIn Founder DM

We are activating paid MetaSwapV3 pilots for wallet/RPC, issuer launch and white-label exchange infrastructure. It is built around metering, proof exports, RFQ/trading APIs and compliance gates. If you are dealing with RPC reliability, token launch infrastructure or exchange backend build-vs-buy, I can send the technical one-pager.

## Proposal Gate

Every proposal must include:

- Package ID and scope.
- Setup fee, pilot fee, monthly recurring fee and usage overage.
- KYB/security/legal activation requirements.
- Payment reference and reconciliation requirement.
- SLA tier and escalation channel.
- No-production-use clause until entitlement review passes.

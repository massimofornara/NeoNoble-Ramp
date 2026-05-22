# NeoNoble Ramp - Transak Enterprise Integration

This integration uses only officially documented Transak surfaces:

- JavaScript SDK: `@transak/ui-js-sdk`
- Create Widget URL: `POST https://api-gateway-stg.transak.com/api/v2/auth/session` and `POST https://api-gateway.transak.com/api/v2/auth/session`
- Partner auth refresh: `POST /partners/api/v2/refresh-token`
- Order status: `GET /partners/api/v2/order/:orderId` and `GET /partners/api/v2/orders`
- Currencies: `GET /api/v2/currencies/crypto-currencies` and `GET /api/v2/currencies/fiat-currencies`
- WebSockets: Pusher public channel `${API_KEY}_${partnerOrderId}`
- Webhooks: signed JWT payload in `data`, verified with the Partner Access Token

Sources verified on 2026-05-21:

- [Transak JavaScript SDK](https://docs.transak.com/docs/transak-sdk)
- [Create Widget URL](https://docs.transak.com/api/public/create-widget-url)
- [Query Parameters](https://docs.transak.com/customization/query-parameters)
- [WebSockets](https://docs.transak.com/docs/websocket-integrations)
- [Webhooks](https://docs.transak.com/docs/webhooks)
- [Get Orders](https://docs.transak.com/api/public/get-orders)
- [Get Order By ID](https://docs.transak.com/api/public/get-order-by-order-id)
- [Refresh Access Token](https://docs.transak.com/reference/refresh-access-token)

## Project Structure

```text
components/TransakWidget.tsx
components/BuyNENOButton.tsx
components/SellNENOButton.tsx
components/SwapNENOButton.tsx
app/api/transak/session/route.ts
app/api/transak/status/route.ts
app/api/transak/webhook/route.ts
app/api/transak/currencies/route.ts
app/api/health/route.ts
app/api/metrics/route.ts
lib/transak/*
types/transak.ts
db/migrations/20260521_transak_enterprise.sql
deploy/k8s/*
deploy/helm/neonoble-ramp/*
deploy/nginx.conf
deploy/cloudflare.md
scripts/deploy.sh
scripts/migrate.sh
scripts/healthcheck.sh
```

## Environment

Staging:

```bash
cp .env.staging .env.local
npm install
npm run dev
```

Production:

```bash
cp .env.production .env.local
npm run build
npm run start
```

Required Transak values:

```bash
TRANSAK_API_KEY=
NEXT_PUBLIC_TRANSAK_API_KEY=
NEXT_PUBLIC_TRANSAK_ENVIRONMENT=STAGING
TRANSAK_API_SECRET=
TRANSAK_ACCESS_TOKEN=
TRANSAK_WEBHOOK_SECRET=
TRANSAK_WIDGET_URL=https://global-stg.transak.com
TRANSAK_API_BASE_URL=https://api-stg.transak.com
TRANSAK_API_GATEWAY_URL=https://api-gateway-stg.transak.com
NEXT_PUBLIC_TRANSAK_PUSHER_APP_KEY=1d9ffac87de599c61283
NEXT_PUBLIC_TRANSAK_PUSHER_CLUSTER=ap2
```

`TRANSAK_API_SECRET` is sent as the documented `api-secret` header only to `POST /partners/api/v2/refresh-token`. `TRANSAK_ACCESS_TOKEN` is reused for session creation, order status, and webhook JWT verification.

## Widget Modes

Implemented official `productsAvailed` modes:

- `BUY`: fiat to NENO on-ramp
- `SELL`: NENO to fiat off-ramp
- `BUY,SELL`: combined Transak mode

The official Transak widget does not document a `SWAP` product. Crypto-to-crypto NENO swaps must remain in NeoNoble’s own swap engine or a separately documented provider integration.

## Official Query Parameters Used

```json
{
  "apiKey": "required",
  "referrerDomain": "required",
  "productsAvailed": "BUY | SELL | BUY,SELL",
  "fiatCurrency": "EUR",
  "defaultFiatCurrency": "EUR",
  "fiatAmount": 100,
  "cryptoCurrencyCode": "NENO",
  "defaultCryptoCurrency": "NENO",
  "cryptoCurrencyList": "NENO,ETH,USDT,USDC,BNB",
  "cryptoAmount": 1,
  "network": "bsc",
  "networks": "bsc,ethereum,polygon",
  "defaultNetwork": "bsc",
  "paymentMethod": "provider-specific value from Transak coverage",
  "walletAddress": "0x...",
  "disableWalletAddressForm": true,
  "walletRedirection": true,
  "email": "user@example.com",
  "partnerOrderId": "internal-id",
  "partnerCustomerId": "customer-id",
  "redirectURL": "https://app.neonoble.io/ramp",
  "themeColor": "#00f5d4",
  "colorMode": "DARK",
  "hideMenu": true,
  "exchangeScreenTitle": "NeoNoble NENO Ramp"
}
```

## SDK Events

The frontend listens to official SDK events:

```text
TRANSAK_WIDGET_INITIALISED
TRANSAK_WIDGET_OPEN
TRANSAK_ORDER_CREATED
TRANSAK_ORDER_SUCCESSFUL
TRANSAK_ORDER_CANCELLED
TRANSAK_ORDER_FAILED
TRANSAK_WIDGET_CLOSE
```

## Webhook Payload

Transak order webhook response examples use this shape before signing:

```json
{
  "webhookData": {
    "id": "37969614-...",
    "status": "COMPLETED",
    "fiatCurrency": "EUR",
    "cryptoCurrency": "ETH",
    "isBuyOrSell": "BUY",
    "fiatAmount": 45,
    "paymentOptionId": "sepa_bank_transfer",
    "network": "ethereum",
    "walletAddress": "0xD902d7E..."
  },
  "eventID": "ORDER_COMPLETED"
}
```

Incoming production webhooks are signed in the `data` field as a JWT. `app/api/transak/webhook/route.ts` verifies `data` with the Partner Access Token before logging or processing it.

Order webhook event IDs implemented:

```text
ORDER_CREATED
ORDER_PAYMENT_VERIFYING
ORDER_PROCESSING
ORDER_COMPLETED
ORDER_FAILED
ORDER_CANCELLED
ORDER_REFUNDED
ORDER_EXPIRED
```

KYC webhook event IDs documented by Transak for whitelabel KYC:

```text
KYC_SUBMITTED
KYC_APPROVED
KYC_REJECTED
```

## Database

```bash
DATABASE_URL=postgresql://...
./scripts/migrate.sh
```

Tables:

- `transactions`
- `kyc_sessions`
- `webhook_events`
- `swap_events`
- `user_wallets`
- `revenue_tracking`

## Docker

```bash
docker compose up --build
docker compose exec app sh scripts/migrate.sh
curl http://localhost:3000/api/health
```

## Kubernetes

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/secrets.yaml
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/ingress.yaml
kubectl apply -f deploy/k8s/autoscaling.yaml
kubectl apply -f deploy/k8s/pdb.yaml
```

Helm:

```bash
helm upgrade --install neonoble-ramp ./deploy/helm/neonoble-ramp \
  --namespace neonoble-ramp --create-namespace \
  --set image.repository=registry.example.com/neonoble-ramp \
  --set image.tag=2026-05-21
```

Rollback:

```bash
helm rollback neonoble-ramp --namespace neonoble-ramp
kubectl -n neonoble-ramp rollout undo deployment/neonoble-ramp
```

## Observability

- `/api/health`: liveness and readiness
- `/api/metrics`: Prometheus metrics
- Docker Compose includes Prometheus, Grafana, and Loki
- Structured logs are JSON lines with `service=neonoble-transak`
- Sentry DSNs are supported via `SENTRY_DSN` and `NEXT_PUBLIC_SENTRY_DSN`

## Security Controls

- Server-side widget session creation only
- Origin validation from `CORS_ORIGINS`
- Redis-backed rate limiting when `REDIS_URL` is configured
- Replay protection for webhook `eventID`
- JWT verification for Transak webhook `data`
- CSP allows Transak, Sumsub KYC, Pusher, and Sentry
- Secrets are never sent to the browser
- Production and staging URLs are isolated by env

## Final Verification Checklist

- `POST /api/v2/auth/session`: documented as Create Widget URL
- `POST /partners/api/v2/refresh-token`: documented refresh token endpoint
- `GET /partners/api/v2/order/:orderId`: documented order lookup
- `GET /partners/api/v2/orders`: documented partner-order filter
- `GET /api/v2/currencies/crypto-currencies`: documented dynamic crypto coverage
- `GET /api/v2/currencies/fiat-currencies`: documented fiat coverage
- `@transak/ui-js-sdk`: documented official SDK import
- Events: only official SDK/WebSocket/Webhook events listed above
- Next.js 15: App Router route handlers and client components
- TypeScript strict: `tsconfig.json` enabled

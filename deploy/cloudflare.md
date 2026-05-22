# Cloudflare Configuration

- SSL/TLS mode: Full strict.
- Always Use HTTPS: enabled.
- HTTP/3: enabled.
- WAF rule: allow `POST /api/transak/webhook` from Transak delivery IP ranges once provided by Transak support.
- Rate limiting:
  - `/api/transak/session`: 60 requests/min/IP in staging, 120 requests/min/IP in production.
  - `/api/transak/status`: 240 requests/min/IP in staging, 600 requests/min/IP in production.
- Cache rules:
  - Bypass cache for `/api/*`.
  - Cache static `/_next/static/*` for 1 year.
- Security headers are emitted by Next.js and nginx; avoid Cloudflare header rewrites that remove CSP `frame-src` or `connect-src` entries for Transak, Sumsub, Pusher, and Sentry.

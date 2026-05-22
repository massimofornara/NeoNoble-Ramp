const path = require('path');

const transakFrameSources = [
  'https://global.transak.com',
  'https://global-stg.transak.com',
  'https://*.transak.com',
  'https://*.transak.xyz',
  'https://*.sumsub.com',
  'https://*.sumsub.io',
];

const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'self'",
  "form-action 'self' https://global.transak.com https://global-stg.transak.com",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://*.transak.com https://*.sumsub.com https://js.sentry-cdn.com",
  "style-src 'self' 'unsafe-inline' https://*.transak.com https://*.sumsub.com",
  "img-src 'self' data: blob: https://*.transak.com https://assets.transak.com https://assets-stg.transak.com https://*.sumsub.com",
  "font-src 'self' data: https://*.transak.com https://*.sumsub.com",
  `frame-src 'self' ${transakFrameSources.join(' ')}`,
  "camera 'self'",
  "microphone 'self'",
  "connect-src 'self' https://api.transak.com https://api-stg.transak.com https://api-gateway.transak.com https://api-gateway-stg.transak.com https://*.transak.com https://*.sumsub.com https://*.sentry.io https://*.pusher.com https://*.pusherapp.com wss://*.pusher.com wss://*.pusherapp.com",
  "worker-src 'self' blob:",
  "upgrade-insecure-requests",
].join('; ');

const nextConfig = {
  output: 'standalone',
  outputFileTracingRoot: path.join(__dirname),
  images: {
    unoptimized: true,
    remotePatterns: [
      { protocol: 'https', hostname: 'assets.transak.com' },
      { protocol: 'https', hostname: 'assets-stg.transak.com' },
      { protocol: 'https', hostname: '*.transak.com' },
    ],
  },
  serverExternalPackages: ['mongodb', 'pg', 'ioredis'],
  webpack(config, { dev }) {
    config.ignoreWarnings = [
      ...(config.ignoreWarnings || []),
      { module: /@opentelemetry/ },
      { module: /@protobufjs\/inquire/ },
    ];
    if (dev) {
      config.watchOptions = {
        poll: 2000,
        aggregateTimeout: 300,
        ignored: ['**/node_modules'],
      };
    }
    return config;
  },
  onDemandEntries: {
    maxInactiveAge: 10000,
    pagesBufferLength: 2,
  },
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          { key: 'Content-Security-Policy', value: csp },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-DNS-Prefetch-Control', value: 'on' },
          { key: 'Permissions-Policy', value: 'camera=(self "https://global.transak.com" "https://global-stg.transak.com"), microphone=(self "https://global.transak.com" "https://global-stg.transak.com"), payment=(self "https://global.transak.com" "https://global-stg.transak.com")' },
          { key: 'Access-Control-Allow-Origin', value: process.env.CORS_ORIGINS || 'https://app.neonoble.io' },
          { key: 'Access-Control-Allow-Methods', value: 'GET, POST, OPTIONS' },
          { key: 'Access-Control-Allow-Headers', value: 'Content-Type, Authorization, X-Request-Id' },
        ],
      },
    ];
  },
};

module.exports = nextConfig;

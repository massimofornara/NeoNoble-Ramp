export function loadConfig(env = process.env) {
  const environment = env.METASWAP_ENV ?? "local";
  return {
    environment,
    port: Number(env.PORT ?? 8080),
    storage: {
      sqlitePath: env.SQLITE_PATH ?? ".data/metaswap.sqlite"
    },
    external: {
      requireLiveAdapters: environment === "production" || env.REQUIRE_LIVE_ADAPTERS === "true"
    },
    security: {
      adminApiKey: env.ADMIN_API_KEY,
      internalHsmMasterKey: env.INTERNAL_HSM_MASTER_KEY
    },
    developerPlatform: developerPlatformConfig(env),
    banking: endpointConfig("BANKING", env),
    wise: wiseConfig(env),
    swift: endpointConfig("SWIFT", env),
    card: endpointConfig("CARD", env),
    custody: endpointConfig("CUSTODY", env),
    marketMaker: endpointConfig("MARKET_MAKER", env),
    hedging: endpointConfig("HEDGING", env),
    aml: endpointConfig("AML", env),
    travelRule: endpointConfig("TRAVEL_RULE", env),
    distribution: distributionConfig(env),
    blockchain: {
      ethereum: rpcConfig("ETHEREUM", env),
      bnb: rpcConfig("BNB", env),
      solana: rpcConfig("SOLANA", env),
      base: rpcConfig("BASE", env),
      polygon: rpcConfig("POLYGON", env)
    }
  };
}

function developerPlatformConfig(env) {
  return {
    bootstrapApiKey: env.DEVELOPER_BOOTSTRAP_API_KEY,
    webhookSecret: env.WEBHOOK_SIGNING_SECRET ?? env.INTERNAL_HSM_MASTER_KEY ?? "metaswap-webhooks"
  };
}

function distributionConfig(env) {
  const fiatDestinations = [];
  for (const index of [1, 2, 3, 4]) {
    const iban = env[`REVENUE_FIAT_IBAN_${index}`];
    if (!iban) continue;
    fiatDestinations.push({
      id: env[`REVENUE_FIAT_DESTINATION_ID_${index}`] ?? `iban-${index}`,
      rail: env[`REVENUE_FIAT_RAIL_${index}`] ?? "SEPA",
      asset: env[`REVENUE_FIAT_ASSET_${index}`] ?? "EUR",
      iban,
      name: env[`REVENUE_FIAT_NAME_${index}`],
      shareBps: Number(env[`REVENUE_FIAT_SHARE_BPS_${index}`] ?? 0)
    });
  }
  return {
    cryptoWallet: env.REVENUE_CRYPTO_WALLET,
    cryptoChain: env.REVENUE_CRYPTO_CHAIN ?? "ethereum",
    fiatDestinations,
    minSweepUsd: Number(env.REVENUE_MIN_SWEEP_USD ?? 25),
    autoSweepEnabled: env.REVENUE_AUTO_SWEEP_ENABLED === "true"
  };
}

function wiseConfig(env) {
  return {
    baseUrl: env.WISE_BASE_URL,
    accessToken: env.WISE_ACCESS_TOKEN,
    profileId: env.WISE_PROFILE_ID,
    balanceId: env.WISE_BALANCE_ID,
    clientCertPath: env.WISE_CLIENT_CERT_PATH,
    clientKeyPath: env.WISE_CLIENT_KEY_PATH,
    caCertPath: env.WISE_CA_CERT_PATH,
    timeoutMs: Number(env.WISE_TIMEOUT_MS ?? 15000)
  };
}

function endpointConfig(prefix, env) {
  return {
    baseUrl: env[`${prefix}_BASE_URL`],
    apiKey: env[`${prefix}_API_KEY`],
    secret: env[`${prefix}_HMAC_SECRET`],
    clientId: env[`${prefix}_CLIENT_ID`],
    timeoutMs: Number(env[`${prefix}_TIMEOUT_MS`] ?? 10000)
  };
}

function rpcConfig(prefix, env) {
  const urls = (env[`${prefix}_RPC_URLS`] ?? env[`${prefix}_RPC_URL`] ?? "")
    .split(",")
    .map((url) => url.trim())
    .filter(Boolean);
  return {
    rpcUrl: urls[0],
    rpcUrls: urls,
    chainId: env[`${prefix}_CHAIN_ID`],
    deployerAddress: env[`${prefix}_DEPLOYER_ADDRESS`],
    tokenFactoryAddress: env[`${prefix}_TOKEN_FACTORY_ADDRESS`]
  };
}

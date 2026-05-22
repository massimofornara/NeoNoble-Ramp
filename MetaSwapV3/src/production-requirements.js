export const REQUIRED_PRODUCTION_KEYS = [
  "ADMIN_API_KEY",
  "INTERNAL_HSM_MASTER_KEY",
  "BANKING_BASE_URL",
  "BANKING_API_KEY",
  "BANKING_HMAC_SECRET",
  "CARD_BASE_URL",
  "CARD_API_KEY",
  "CARD_HMAC_SECRET",
  "CUSTODY_BASE_URL",
  "CUSTODY_API_KEY",
  "CUSTODY_HMAC_SECRET",
  "MARKET_MAKER_BASE_URL",
  "MARKET_MAKER_API_KEY",
  "MARKET_MAKER_HMAC_SECRET",
  "HEDGING_BASE_URL",
  "HEDGING_API_KEY",
  "HEDGING_HMAC_SECRET",
  "AML_BASE_URL",
  "AML_API_KEY",
  "AML_HMAC_SECRET",
  "TRAVEL_RULE_BASE_URL",
  "TRAVEL_RULE_API_KEY",
  "TRAVEL_RULE_HMAC_SECRET",
  "ETHEREUM_RPC_URLS",
  "ETHEREUM_TOKEN_FACTORY_ADDRESS",
  "BNB_RPC_URLS",
  "BNB_TOKEN_FACTORY_ADDRESS",
  "SOLANA_RPC_URLS",
  "SOLANA_TOKEN_FACTORY_ADDRESS",
  "BASE_RPC_URLS",
  "BASE_TOKEN_FACTORY_ADDRESS",
  "POLYGON_RPC_URLS",
  "POLYGON_TOKEN_FACTORY_ADDRESS"
];

export function missingProductionKeys(env = process.env) {
  return REQUIRED_PRODUCTION_KEYS.filter((key) => !env[key] || String(env[key]).trim() === "");
}

export function assertProductionContract(env = process.env) {
  const missing = missingProductionKeys(env);
  if (env.METASWAP_ENV !== "production") missing.unshift("METASWAP_ENV=production");
  if (missing.length) throw new Error(`Production contract incomplete: ${missing.join(", ")}`);
  return { status: "complete", requiredKeys: REQUIRED_PRODUCTION_KEYS.length };
}

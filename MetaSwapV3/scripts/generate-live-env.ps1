param(
  [string]$OutputPath = ".env.production",
  [switch]$Overwrite
)

$ErrorActionPreference = "Stop"

if ((Test-Path $OutputPath) -and -not $Overwrite) {
  throw "$OutputPath already exists. Use -Overwrite to replace it."
}

function New-Secret([int]$Bytes = 32) {
  $buffer = New-Object byte[] $Bytes
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $rng.GetBytes($buffer)
  }
  finally {
    $rng.Dispose()
  }
  return ([BitConverter]::ToString($buffer) -replace "-", "").ToLowerInvariant()
}

$values = [ordered]@{
  METASWAP_ENV = "production"
  PORT = "8080"
  SQLITE_PATH = "/var/lib/metaswap/metaswap.sqlite"
  REQUIRE_LIVE_ADAPTERS = "true"
  ADMIN_API_KEY = New-Secret 32
  INTERNAL_HSM_MASTER_KEY = New-Secret 64

  BANKING_BASE_URL = ""
  BANKING_API_KEY = ""
  BANKING_HMAC_SECRET = ""
  CARD_BASE_URL = ""
  CARD_API_KEY = ""
  CARD_HMAC_SECRET = ""
  CUSTODY_BASE_URL = ""
  CUSTODY_API_KEY = ""
  CUSTODY_HMAC_SECRET = ""
  MARKET_MAKER_BASE_URL = ""
  MARKET_MAKER_API_KEY = ""
  MARKET_MAKER_HMAC_SECRET = ""
  HEDGING_BASE_URL = ""
  HEDGING_API_KEY = ""
  HEDGING_HMAC_SECRET = ""
  AML_BASE_URL = ""
  AML_API_KEY = ""
  AML_HMAC_SECRET = ""
  TRAVEL_RULE_BASE_URL = ""
  TRAVEL_RULE_API_KEY = ""
  TRAVEL_RULE_HMAC_SECRET = ""

  ETHEREUM_RPC_URLS = "https://ethereum-rpc.publicnode.com,https://rpc.ankr.com/eth"
  ETHEREUM_CHAIN_ID = "1"
  ETHEREUM_TOKEN_FACTORY_ADDRESS = ""
  BNB_RPC_URLS = "https://bsc-rpc.publicnode.com,https://rpc.ankr.com/bsc"
  BNB_CHAIN_ID = "56"
  BNB_TOKEN_FACTORY_ADDRESS = ""
  SOLANA_RPC_URLS = "https://api.mainnet-beta.solana.com"
  SOLANA_CHAIN_ID = "mainnet-beta"
  SOLANA_TOKEN_FACTORY_ADDRESS = ""
  BASE_RPC_URLS = "https://base-rpc.publicnode.com,https://mainnet.base.org"
  BASE_CHAIN_ID = "8453"
  BASE_TOKEN_FACTORY_ADDRESS = ""
  POLYGON_RPC_URLS = "https://polygon-bor-rpc.publicnode.com,https://polygon-rpc.com"
  POLYGON_CHAIN_ID = "137"
  POLYGON_TOKEN_FACTORY_ADDRESS = ""
}

$content = foreach ($entry in $values.GetEnumerator()) {
  "$($entry.Key)=$($entry.Value)"
}

Set-Content -Path $OutputPath -Value $content -Encoding UTF8

$regulated = @(
  "BANKING_*",
  "CARD_*",
  "CUSTODY_*",
  "MARKET_MAKER_*",
  "HEDGING_*",
  "AML_*",
  "TRAVEL_RULE_*",
  "*_TOKEN_FACTORY_ADDRESS"
)

[pscustomobject]@{
  output = (Resolve-Path $OutputPath).Path
  generatedInternalSecrets = @("ADMIN_API_KEY", "INTERNAL_HSM_MASTER_KEY")
  configuredMainnetRpc = @("Ethereum", "BNB Chain", "Solana", "Base", "Polygon")
  stillRequiresRegulatedValues = $regulated
} | ConvertTo-Json

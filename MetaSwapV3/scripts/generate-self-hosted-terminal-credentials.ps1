param(
  [string]$EnvPath = ".env.production"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $EnvPath)) {
  powershell -ExecutionPolicy Bypass -File scripts/generate-live-env.ps1 -OutputPath $EnvPath | Out-Null
}

function New-Secret([int]$Bytes = 32) {
  $buffer = New-Object byte[] $Bytes
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
  return ([BitConverter]::ToString($buffer) -replace "-", "").ToLowerInvariant()
}

function Read-Env([string]$Path) {
  $map = [ordered]@{}
  Get-Content $Path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $idx = $line.IndexOf("=")
    if ($idx -lt 1) { return }
    $map[$line.Substring(0, $idx)] = $line.Substring($idx + 1)
  }
  return $map
}

function Write-Env([string]$Path, $Map) {
  $content = foreach ($entry in $Map.GetEnumerator()) { "$($entry.Key)=$($entry.Value)" }
  Set-Content -Path $Path -Value $content -Encoding UTF8
}

$envMap = Read-Env $EnvPath
$base = "http://127.0.0.1:8080/internal/terminal"

$providers = @(
  "BANKING",
  "CARD",
  "CUSTODY",
  "MARKET_MAKER",
  "HEDGING",
  "AML",
  "TRAVEL_RULE"
)

foreach ($provider in $providers) {
  $envMap["${provider}_BASE_URL"] = "$base/$($provider.ToLowerInvariant())"
  $envMap["${provider}_API_KEY"] = "msv3_$($provider.ToLowerInvariant())_$(New-Secret 16)"
  $envMap["${provider}_HMAC_SECRET"] = New-Secret 32
}

Write-Env $EnvPath $envMap

[pscustomobject]@{
  env = (Resolve-Path $EnvPath).Path
  generated = $providers
  terminalBaseUrl = $base
  warning = "Generated credentials are MetaSwap self-hosted terminal credentials, not regulated bank/PSP/card/custody authorizations."
} | ConvertTo-Json

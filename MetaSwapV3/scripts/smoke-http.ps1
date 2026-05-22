$ErrorActionPreference = "Stop"

function Get-EnvValue($Path, $Key) {
  if (-not (Test-Path $Path)) { return "" }
  $line = Get-Content $Path | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
  if (-not $line) { return "" }
  return ($line -replace "^$Key=", "").Trim().Trim('"').Trim("'")
}

$root = Split-Path -Parent $PSScriptRoot
$port = if ($env:PORT) { [int]$env:PORT } else { 8080 }
$baseUrl = "http://127.0.0.1:$port"
$adminApiKey = if ($env:ADMIN_API_KEY) { $env:ADMIN_API_KEY } else { Get-EnvValue (Join-Path $root ".env.production") "ADMIN_API_KEY" }
$adminHeaders = @{}
if ($adminApiKey) { $adminHeaders["x-admin-api-key"] = $adminApiKey }
$symbol = ("SMK" + [Guid]::NewGuid().ToString("N").Substring(0, 6)).ToUpper()
$smokeDb = Join-Path $root (".data\metaswap.smoke." + [Guid]::NewGuid().ToString("N") + ".sqlite")
$previousSqlitePath = $env:SQLITE_PATH

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = "node"
$psi.Arguments = "--use-system-ca src/server.js"
$psi.WorkingDirectory = $root
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$env:SQLITE_PATH = $smokeDb
$process = [System.Diagnostics.Process]::Start($psi)

try {
  Start-Sleep -Seconds 1
  if ($process.HasExited) {
    throw "Server exited early with code $($process.ExitCode)"
  }

  $health = Invoke-RestMethod "$baseUrl/health"
  if ($health.status -ne "ok") {
    throw "Health check failed"
  }

  $depositBody = @{
    userId = "user-eu-1"
    asset = "EUR"
    amount = 10000
    rail = "SEPA"
  } | ConvertTo-Json -Depth 5
  $deposit = Invoke-RestMethod "$baseUrl/fiat/deposit" -Method Post -ContentType "application/json" -Body $depositBody

  $tokenBody = @{
    issuerId = "issuer-1"
    symbol = $symbol
    name = "Smoke Asset"
    maxSupply = 100000000
    issuePriceUsd = 0.25
    chains = @("ethereum", "solana")
    micaClassification = "utility"
  } | ConvertTo-Json -Depth 5
  $token = Invoke-RestMethod "$baseUrl/tokens" -Method Post -ContentType "application/json" -Body $tokenBody

  $buyBody = @{
    userId = "user-eu-1"
    symbol = $symbol
    quoteAsset = "EUR"
    side = "buy"
    amount = 1000
  } | ConvertTo-Json -Depth 5
  $buy = Invoke-RestMethod "$baseUrl/orders" -Method Post -ContentType "application/json" -Body $buyBody
  if ($buy.status -ne "filled") {
    throw "RFQ buy did not fill"
  }

  $sellBody = @{
    userId = "user-eu-1"
    symbol = $symbol
    quoteAsset = "EUR"
    side = "sell"
    amount = 100
  } | ConvertTo-Json -Depth 5
  $sell = Invoke-RestMethod "$baseUrl/orders" -Method Post -ContentType "application/json" -Body $sellBody
  if ($sell.status -ne "filled") {
    throw "RFQ sell did not fill"
  }

  $withdrawBody = @{
    userId = "user-eu-1"
    asset = $symbol
    amount = 10
    chain = "ethereum"
    address = "0x2222222222222222222222222222222222222222"
  } | ConvertTo-Json -Depth 5
  $withdraw = Invoke-RestMethod "$baseUrl/custody/withdraw" -Method Post -ContentType "application/json" -Body $withdrawBody

  $payoutBody = @{
    userId = "user-eu-1"
    asset = "EUR"
    amount = 100
    rail = "SEPA"
    destination = @{
      iban = "DE89370400440532013000"
      name = "Demo User"
    }
  } | ConvertTo-Json -Depth 5
  $payout = Invoke-RestMethod "$baseUrl/fiat/payout" -Method Post -ContentType "application/json" -Body $payoutBody
  $proof = Invoke-RestMethod "$baseUrl/proof/reserves-liabilities"
  $exposure = Invoke-RestMethod "$baseUrl/treasury/exposure/$symbol"
  $stressBody = @{
    symbol = $symbol
    shockPercent = 0.35
  } | ConvertTo-Json -Depth 5
  $stress = Invoke-RestMethod "$baseUrl/admin/stress-test" -Method Post -ContentType "application/json" -Headers $adminHeaders -Body $stressBody
  $reconcile = Invoke-RestMethod "$baseUrl/admin/reconcile" -Method Post -Headers $adminHeaders
  $settlement = Invoke-RestMethod "$baseUrl/settlement/status"
  $metrics = Invoke-RestMethod "$baseUrl/metrics"
  $providers = Invoke-RestMethod "$baseUrl/providers"
  $regions = Invoke-RestMethod "$baseUrl/regions/status"

  [pscustomobject]@{
    health = $health.status
    deposit = $deposit.status
    token = $token.symbol
    tokenLifecycle = $token.lifecycle
    buy = $buy.status
    buyVenue = $buy.venue
    sell = $sell.status
    withdrawal = $withdraw.status
    payout = $payout.status
    proof = $proof.reserveRoot.Substring(0, 12)
    exposure = $exposure.symbol
    stress = $stress.pass
    reconciliation = $reconcile.status
    settlementEntries = $settlement.ledgerEntries
    metrics = $metrics.Contains("metaswap_events_total")
    providers = $providers.Count
    regions = $regions.Count
    baseUrl = $baseUrl
  } | ConvertTo-Json
}
catch {
  $response = $_.Exception.Response
  if ($response -and $response.GetResponseStream()) {
    $reader = [System.IO.StreamReader]::new($response.GetResponseStream())
    $body = $reader.ReadToEnd()
    throw "$($_.Exception.Message) $body"
  }
  throw
}
finally {
  if ($process -and -not $process.HasExited) {
    $process.Kill()
    $process.WaitForExit()
  }
  if (Test-Path $smokeDb) { Remove-Item -LiteralPath $smokeDb -Force }
  $env:SQLITE_PATH = $previousSqlitePath
}

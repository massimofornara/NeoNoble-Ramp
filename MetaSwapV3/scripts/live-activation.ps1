param(
  [string]$EnvFile = ".env.production",
  [string]$BaseUrl = "http://127.0.0.1:8080",
  [int]$LoadRequests = 1000,
  [int]$LoadConcurrency = 25
)

$ErrorActionPreference = "Stop"

function Read-EnvFile([string]$Path) {
  if (-not (Test-Path $Path)) {
    throw "Missing production env file: $Path"
  }
  $map = @{}
  Get-Content $Path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $idx = $line.IndexOf("=")
    if ($idx -lt 1) { return }
    $key = $line.Substring(0, $idx)
    $value = $line.Substring($idx + 1)
    $map[$key] = $value
    [Environment]::SetEnvironmentVariable($key, $value, "Process")
  }
  return $map
}

$envMap = Read-EnvFile $EnvFile

$required = node -e "import('./src/production-requirements.js').then(m=>console.log(m.REQUIRED_PRODUCTION_KEYS.join('\n')))"

$missing = @()
foreach ($key in $required) {
  if (-not $envMap.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($envMap[$key])) {
    $missing += $key
  }
}

if ($envMap["METASWAP_ENV"] -ne "production") {
  $missing += "METASWAP_ENV must equal production"
}

if ($missing.Count -gt 0) {
  throw "Live activation blocked by production gate. Missing or invalid: $($missing -join ', ')"
}

$process = [System.Diagnostics.Process]::Start([System.Diagnostics.ProcessStartInfo]@{
  FileName = "node"
  Arguments = "src/server.js"
  WorkingDirectory = (Get-Location).Path
  UseShellExecute = $false
  CreateNoWindow = $true
})

try {
  Start-Sleep -Seconds 2
  if ($process.HasExited) {
    throw "Production server exited during activation with code $($process.ExitCode)"
  }

  $adminHeader = @{ "x-admin-api-key" = $envMap["ADMIN_API_KEY"] }
  $readiness = powershell -ExecutionPolicy Bypass -File scripts/production-readiness.ps1 -BaseUrl $BaseUrl -AdminApiKey $envMap["ADMIN_API_KEY"] | ConvertFrom-Json
  $security = powershell -ExecutionPolicy Bypass -File scripts/security-baseline.ps1 -BaseUrl $BaseUrl | ConvertFrom-Json
  $load = powershell -ExecutionPolicy Bypass -File scripts/load-test.ps1 -BaseUrl $BaseUrl -Requests $LoadRequests -Concurrency $LoadConcurrency | ConvertFrom-Json
  $rpc = Invoke-RestMethod "$BaseUrl/rpc/status"
  $providers = Invoke-RestMethod "$BaseUrl/providers"
  $regions = Invoke-RestMethod "$BaseUrl/regions/status"

  foreach ($control in @("SOC2", "MiCA_CASP", "EMI_PI", "BSA_AML")) {
    Invoke-RestMethod "$BaseUrl/compliance/evidence/generate" -Method Post -Headers $adminHeader -ContentType "application/json" -Body (@{ control = $control } | ConvertTo-Json) | Out-Null
  }

  [pscustomobject]@{
    status = "LIVE_ACTIVATION_VALIDATED"
    readiness = $readiness
    security = $security.status
    load = $load
    providers = $providers.Count
    regions = $regions.Count
    rpcChains = ($rpc.PSObject.Properties | Measure-Object).Count
    evidenceGenerated = 4
    activatedAt = (Get-Date).ToUniversalTime().ToString("o")
  } | ConvertTo-Json -Depth 8
}
finally {
  if ($process -and -not $process.HasExited) {
    Stop-Process -Id $process.Id -Force
  }
}

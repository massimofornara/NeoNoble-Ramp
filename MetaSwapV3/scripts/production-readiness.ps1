param(
  [string]$BaseUrl = "http://127.0.0.1:8080",
  [string]$AdminApiKey = ""
)

$ErrorActionPreference = "Stop"
$headers = @{}
if ($AdminApiKey) { $headers["x-admin-api-key"] = $AdminApiKey }

$health = Invoke-RestMethod "$BaseUrl/health"
$providers = Invoke-RestMethod "$BaseUrl/providers"
$regions = Invoke-RestMethod "$BaseUrl/regions/status"
$proof = Invoke-RestMethod "$BaseUrl/proof/reserves-liabilities"
$regulatory = Invoke-RestMethod "$BaseUrl/compliance/regulatory"

[pscustomobject]@{
  health = $health.status
  providers = $providers.Count
  activeRegions = @($regions | Where-Object { $_.status -eq "active" }).Count
  reserveRoot = $proof.reserveRoot
  controls = ($regulatory.PSObject.Properties | Measure-Object).Count
} | ConvertTo-Json

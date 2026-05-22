param(
  [string]$BaseUrl = "http://127.0.0.1:8080"
)

$ErrorActionPreference = "Stop"
$response = Invoke-WebRequest "$BaseUrl/health" -UseBasicParsing
$required = @(
  "x-content-type-options",
  "x-frame-options",
  "referrer-policy",
  "content-security-policy",
  "cache-control"
)
$missing = @()
foreach ($header in $required) {
  if (-not $response.Headers[$header]) { $missing += $header }
}
if ($missing.Count -gt 0) {
  throw "Missing security headers: $($missing -join ', ')"
}
[pscustomobject]@{
  status = "passed"
  checkedHeaders = $required
} | ConvertTo-Json

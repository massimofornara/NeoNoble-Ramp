param(
  [int]$Requests = 1000,
  [int]$Concurrency = 25,
  [string]$BaseUrl = "http://127.0.0.1:8080"
)

$ErrorActionPreference = "Stop"
$queue = [System.Collections.Concurrent.ConcurrentQueue[int]]::new()
1..$Requests | ForEach-Object { $queue.Enqueue($_) }
$latencies = [System.Collections.Concurrent.ConcurrentBag[double]]::new()
$errors = [System.Collections.Concurrent.ConcurrentBag[string]]::new()

$jobs = 1..$Concurrency | ForEach-Object {
  Start-Job -ScriptBlock {
    param($workerId, $requests, $concurrency, $baseUrl)
    $rows = @()
    for ($i = $workerId; $i -le $requests; $i += $concurrency) {
      $sw = [System.Diagnostics.Stopwatch]::StartNew()
      try {
        Invoke-RestMethod "$baseUrl/health" | Out-Null
        $sw.Stop()
        $rows += [pscustomobject]@{ ok = $true; ms = $sw.Elapsed.TotalMilliseconds }
      } catch {
        $sw.Stop()
        $rows += [pscustomobject]@{ ok = $false; ms = $sw.Elapsed.TotalMilliseconds }
      }
    }
    $rows
  } -ArgumentList $_, $Requests, $Concurrency, $BaseUrl
}

Wait-Job $jobs | Out-Null
$results = Receive-Job $jobs
Remove-Job $jobs

$values = @($results | Where-Object { $_.ok } | ForEach-Object { $_.ms })
$errorCount = @($results | Where-Object { -not $_.ok }).Count
$avg = ($values | Measure-Object -Average).Average
$sorted = $values | Sort-Object
$p95Index = [Math]::Min($sorted.Count - 1, [Math]::Floor($sorted.Count * 0.95))
[pscustomobject]@{
  requests = $Requests
  concurrency = $Concurrency
  success = $values.Count
  errors = $errorCount
  avgMs = [Math]::Round($avg, 2)
  p95Ms = [Math]::Round($sorted[$p95Index], 2)
} | ConvertTo-Json

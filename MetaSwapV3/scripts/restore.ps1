param(
  [Parameter(Mandatory = $true)]
  [string]$BackupPath
)

$ErrorActionPreference = "Stop"
$target = if ($env:SQLITE_PATH) { $env:SQLITE_PATH } else { ".data/metaswap.sqlite" }
$targetDir = Split-Path -Parent $target
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
Copy-Item $BackupPath $target -Force
Write-Output "restored:$target"

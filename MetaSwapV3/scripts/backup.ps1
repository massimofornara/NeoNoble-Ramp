$ErrorActionPreference = "Stop"

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$source = if ($env:SQLITE_PATH) { $env:SQLITE_PATH } else { ".data/metaswap.sqlite" }
$targetDir = if ($env:BACKUP_DIR) { $env:BACKUP_DIR } else { ".backups" }

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
Copy-Item $source "$targetDir/metaswap-$timestamp.sqlite"
Write-Output "$targetDir/metaswap-$timestamp.sqlite"

# ==============================================================================
# Nova v2.0 Configuration & Data Backup Script (PowerShell / Windows)
# ==============================================================================

$backupDir = Join-Path $PSScriptRoot "backups"
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$archiveName = Join-Path $backupDir "nova_v2_backup_${timestamp}.zip"

Write-Host "Creating Nova v2.0 Backup Archive: $archiveName..." -ForegroundColor Cyan

$sourceDirs = @()
if (Test-Path "logs") { $sourceDirs += "logs" }
if (Test-Path ".env") { $sourceDirs += ".env" }

if ($sourceDirs.Count -gt 0) {
    Compress-Archive -Path $sourceDirs -DestinationPath $archiveName -Force
    Write-Host "Backup created successfully: $archiveName" -ForegroundColor Green
} else {
    Write-Host "No logs or configuration found to backup." -ForegroundColor Yellow
}

param (
    [Parameter(Mandatory=$true)]
    [string]$ArchivePath
)

# Nova v2.0 Windows Restore Script
Write-Host "Restoring Nova v2.0 from $ArchivePath..." -ForegroundColor Cyan

if (-not (Test-Path $ArchivePath)) {
    Write-Host "Error: Archive file '$ArchivePath' not found." -ForegroundColor Red
    exit 1
}

Expand-Archive -Path $ArchivePath -DestinationPath "." -Force
Write-Host "Nova v2.0 restored successfully!" -ForegroundColor Green

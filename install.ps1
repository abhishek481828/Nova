# ==============================================================================
# Nova v2.0 Production Installation Script (PowerShell / Windows)
# ==============================================================================

Write-Host "[*] Installing Nova v2.0 Core Environment on Windows..." -ForegroundColor Cyan

# Create Python virtual environment if not present
if (-not (Test-Path ".venv")) {
    Write-Host "[+] Creating Python 3.12 virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

$venvPip = Join-Path $PSScriptRoot ".venv\Scripts\pip.exe"

Write-Host "[+] Installing Core Python Dependencies..." -ForegroundColor Green
& $venvPip install --upgrade pip setuptools wheel
if (Test-Path "requirements.txt") {
    & $venvPip install -r requirements.txt
}

# Install FastAPI and Uvicorn for Companion Gateway
& $venvPip install fastapi uvicorn pillow

if (Test-Path ".env.example" -and -not (Test-Path ".env")) {
    Write-Host "[+] Generating initial .env configuration..." -ForegroundColor Cyan
    Copy-Item .env.example .env
}

# Ensure log and backup directories exist
if (-not (Test-Path "logs")) { New-Item -ItemType Directory -Force -Path "logs" | Out-Null }
if (-not (Test-Path "backups")) { New-Item -ItemType Directory -Force -Path "backups" | Out-Null }

Write-Host "[OK] Nova v2.0 Windows Environment Installation Complete!" -ForegroundColor Green
Write-Host "Run '.\start.ps1' to launch Nova." -ForegroundColor Magenta

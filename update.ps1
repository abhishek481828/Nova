# Nova v2.0 Windows Update Script
Write-Host "Updating Nova v2.0..." -ForegroundColor Cyan

# Check Git
if (Test-Path ".git") {
    Write-Host "Pulling latest git changes..." -ForegroundColor Yellow
    git pull --rebase
}

# Update Python virtual environment packages
if (Test-Path ".venv\Scripts\pip.exe") {
    Write-Host "Updating Python dependencies..." -ForegroundColor Yellow
    & ".\.venv\Scripts\pip.exe" install --upgrade -r requirements.txt
}

Write-Host "Nova v2.0 update complete!" -ForegroundColor Green

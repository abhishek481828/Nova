# ==============================================================================
# Nova v2.0 Launcher (PowerShell / Windows)
# ==============================================================================

param(
    [switch]$Check,
    [switch]$Voice,
    [switch]$Text,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

if ($Check) {
    Write-Host "Nova v2.0 Start Script OK"
    exit 0
}

Write-Host "[*] Starting Nova v2.0 Core REPL..." -ForegroundColor Magenta

if (-not (Test-Path "logs")) {
    New-Item -ItemType Directory -Force -Path "logs" | Out-Null
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    $venvPython = "python"
}

$cliArgs = @()
if ($Voice) { $cliArgs += "--voice" }
if ($Text)  { $cliArgs += "--text" }
if ($RemainingArgs) { $cliArgs += $RemainingArgs }

$env:PYTHONPATH = "."
& $venvPython -m nova.core.cli @cliArgs

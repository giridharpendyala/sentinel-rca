<#
.SYNOPSIS
  One-time (idempotent) setup: creates the Python venv, installs agent/eval
  dependencies, installs the shared telemetry package, and copies .env.example
  to .env if it doesn't exist yet.
#>
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".\.env")) {
  Write-Host "Creating .env from .env.example - fill in OPENAI_API_KEY before running the demo." -ForegroundColor Yellow
  Copy-Item ".env.example" ".env"
} else {
  Write-Host ".env already exists, leaving it as-is." -ForegroundColor DarkGray
}

if (-not (Test-Path ".\.venv")) {
  Write-Host "Creating Python 3.12 virtual environment..." -ForegroundColor Cyan
  py -3.12 -m venv .venv
} else {
  Write-Host ".venv already exists, reusing it." -ForegroundColor DarkGray
}

$py = ".\.venv\Scripts\python.exe"

Write-Host "Upgrading pip..." -ForegroundColor Cyan
& $py -m pip install --upgrade pip --quiet

Write-Host "Installing agent/eval dependencies..." -ForegroundColor Cyan
& $py -m pip install -r requirements-agents.txt --quiet

Write-Host "Installing shared telemetry package (editable)..." -ForegroundColor Cyan
& $py -m pip install -e libs\telemetry --quiet

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next: edit .env and set a real OPENAI_API_KEY, then run scripts\start-all.ps1"

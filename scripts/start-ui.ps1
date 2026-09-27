<#
.SYNOPSIS
  Starts (or restarts) the native agents-api / Web Test Page server on port 58010.
  Ensures any running instance is stopped and reloaded with the latest .env variables.
.EXAMPLE
  .\scripts\start-ui.ps1
#>
param(
  [switch]$NoBrowser
)

$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$pidDir = Join-Path $root ".pids"
if (-not (Test-Path $pidDir)) {
  New-Item -ItemType Directory -Path $pidDir | Out-Null
}
$pidFile = Join-Path $pidDir "agents-api.pid"

# Stop any process listening on 58010
$existingConn = Get-NetTCPConnection -LocalPort 58010 -State Listen -ErrorAction SilentlyContinue
if ($existingConn) {
  foreach ($c in $existingConn) {
    Write-Host "Stopping existing process on port 58010 (PID $($c.OwningProcess))..." -ForegroundColor Yellow
    Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
  }
  Start-Sleep -Seconds 1
}

if (Test-Path $pidFile) {
  $oldPid = Get-Content $pidFile -ErrorAction SilentlyContinue
  if ($oldPid) {
    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
  }
  Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

$ErrorActionPreference = "Stop"

Write-Host "Starting agents-api server on http://localhost:58010 (loading latest .env)..." -ForegroundColor Cyan
$pythonExe = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
  $pythonExe = "python"
}

$proc = Start-Process -FilePath $pythonExe -ArgumentList "-m uvicorn agents.api:app --host 0.0.0.0 --port 58010" -PassThru -WindowStyle Hidden
$proc.Id | Out-File -FilePath $pidFile -Encoding ascii

Write-Host "agents-api started with PID $($proc.Id)" -ForegroundColor Green
Write-Host "Web Test Page URL: http://localhost:58010" -ForegroundColor Cyan

Start-Sleep -Seconds 2

if (-not $NoBrowser) {
  Start-Process "http://localhost:58010"
}

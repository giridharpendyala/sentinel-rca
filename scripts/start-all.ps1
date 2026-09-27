<#
.SYNOPSIS
  Starts the full capstone stack (observability infra + Langfuse + synthetic app)
  on its fixed 5xxxx ports. Safe to re-run - only starts what isn't already running.
#>
param(
  [switch]$Build
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$ports = @{
  "Prometheus"          = 59090
  "Grafana"             = 53300
  "Loki"                = 53100
  "Tempo"               = 53201
  "OTel Collector grpc" = 54317
  "OTel Collector http" = 54318
  "Langfuse web"        = 54000
  "Langfuse worker"     = 54001
  "Langfuse Postgres"   = 55500
  "Langfuse ClickHouse" = 58123
  "Langfuse Redis"      = 56380
  "Langfuse MinIO api"  = 59002
  "incident-controller" = 58006
  "checkout-service"    = 58001
  "cart-service"        = 58002
  "pricing-service"     = 58003
  "payment-service"     = 58004
  "load-generator"      = 58005
}

Write-Host "Checking Docker Desktop..." -ForegroundColor Cyan
$dockerOk = $false
try {
  cmd /c "docker info >nul 2>&1"
  if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
} catch {
  $dockerOk = $false
}

if (-not $dockerOk) {
  Write-Host "Docker daemon not reachable - launching Docker Desktop..." -ForegroundColor Yellow
  if (Test-Path "C:\Program Files\Docker\Docker\Docker Desktop.exe") {
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  } else {
    Write-Warning "Docker Desktop executable not found at default location. Please start Docker Desktop manually."
  }
  $ready = $false
  for ($i = 0; $i -lt 30; $i++) {
    Write-Host "Waiting for Docker daemon to become ready... ($($i * 5)s)" -ForegroundColor DarkGray
    Start-Sleep -Seconds 5
    cmd /c "docker info >nul 2>&1"
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
  }
  if (-not $ready) { throw "Docker did not become ready in time. Please start Docker Desktop and re-run." }
}


Write-Host "Checking for port conflicts with processes outside this stack..." -ForegroundColor Cyan
$composeIds = (docker compose ps -q) 2>$null
foreach ($name in $ports.Keys) {
  $port = $ports[$name]
  $conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
  if ($conn) {
    $ownedByCompose = $false
    foreach ($c in $conn) {
      $procId = $c.OwningProcess
      $procName = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName
      if ($procName -in @("com.docker.backend", "docker", "vpnkit", "com.docker.proxy")) { $ownedByCompose = $true }
    }
    if (-not $ownedByCompose) {
      Write-Warning "$name`'s port $port is in use by a non-Docker process. Update docs/ports.md and docker-compose.yml if this persists."
    }
  }
}

if ($Build) {
  Write-Host "Building synthetic-app images..." -ForegroundColor Cyan
  docker compose build
}

Write-Host "Starting all containers..." -ForegroundColor Cyan
docker compose up -d

Write-Host "Waiting for health checks..." -ForegroundColor Cyan
Start-Sleep -Seconds 5
docker compose ps

Write-Host ""
Write-Host "Stack is up. See docs/ports.md for the full port table." -ForegroundColor Green
Write-Host "  Grafana:  http://localhost:53300"
Write-Host "  Langfuse: http://localhost:54000"
Write-Host "  Prometheus: http://localhost:59090"

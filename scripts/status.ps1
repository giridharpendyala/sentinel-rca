<#
.SYNOPSIS
  Reports health of every fixed-port service in the capstone stack, plus any
  native (non-Docker) agents-api process tracked via a PID file.
#>
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "=== Docker containers ===" -ForegroundColor Cyan
docker compose ps

Write-Host ""
Write-Host "=== HTTP health checks ===" -ForegroundColor Cyan
$checks = @(
  @{ Name = "Prometheus";           Url = "http://localhost:59090/-/healthy" }
  @{ Name = "Loki";                 Url = "http://localhost:53100/ready" }
  @{ Name = "Tempo";                Url = "http://localhost:53201/ready" }
  @{ Name = "Grafana";              Url = "http://localhost:53300/api/health" }
  @{ Name = "Langfuse web";         Url = "http://localhost:54000/api/public/health" }
  @{ Name = "Langfuse worker";      Url = "http://localhost:54001/api/health" }
  @{ Name = "incident-controller";  Url = "http://localhost:58006/healthz" }
  @{ Name = "checkout-service";     Url = "http://localhost:58001/healthz" }
  @{ Name = "cart-service";         Url = "http://localhost:58002/healthz" }
  @{ Name = "pricing-service";      Url = "http://localhost:58003/healthz" }
  @{ Name = "payment-service";      Url = "http://localhost:58004/healthz" }
  @{ Name = "load-generator";       Url = "http://localhost:58005/healthz" }
)

foreach ($c in $checks) {
  try {
    $resp = Invoke-WebRequest -Uri $c.Url -TimeoutSec 3 -UseBasicParsing
    $status = if ($resp.StatusCode -eq 200) { "OK" } else { "HTTP $($resp.StatusCode)" }
    $color = if ($resp.StatusCode -eq 200) { "Green" } else { "Yellow" }
  } catch {
    $status = "UNREACHABLE"
    $color = "Red"
  }
  Write-Host ("  {0,-22} {1}" -f $c.Name, $status) -ForegroundColor $color
}

Write-Host ""
Write-Host "=== Native processes (agents-api, if running) ===" -ForegroundColor Cyan
$pidFile = Join-Path $root ".pids\agents-api.pid"
if (Test-Path $pidFile) {
  $procId = Get-Content $pidFile
  $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
  if ($proc) {
    Write-Host "  agents-api running (PID $procId)" -ForegroundColor Green
  } else {
    Write-Host "  agents-api PID file exists but process $procId is not running (stale)" -ForegroundColor Yellow
  }
} else {
  Write-Host "  agents-api not started (no PID file) - this is fine, it's optional" -ForegroundColor DarkGray
}

<#
.SYNOPSIS
  Stops all capstone containers WITHOUT removing them or their volumes.
  Never touches processes outside this project (never "kill all node/docker").
.PARAMETER Full
  Also removes containers, networks, and volumes (docker compose down -v).
  Only use this when you want a truly clean slate - it deletes Postgres/
  ClickHouse/Grafana/Prometheus/Loki/Tempo data.
#>
param(
  [switch]$Full
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($Full) {
  Write-Host "Removing containers, networks, and volumes (full reset)..." -ForegroundColor Yellow
  docker compose down -v
} else {
  Write-Host "Stopping containers (data volumes preserved)..." -ForegroundColor Cyan
  docker compose stop
}

docker compose ps -a

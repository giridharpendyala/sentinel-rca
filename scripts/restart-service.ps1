<#
.SYNOPSIS
  Restarts exactly one compose service by name. Never restarts everything,
  never touches processes outside this project.
.EXAMPLE
  .\scripts\restart-service.ps1 -Name payment-service
#>
param(
  [Parameter(Mandatory = $true)]
  [string]$Name
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$validServices = (docker compose config --services) -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ }

if ($Name -notin $validServices) {
  Write-Host "Unknown service '$Name'. Valid services are:" -ForegroundColor Red
  $validServices | ForEach-Object { Write-Host "  $_" }
  exit 1
}

Write-Host "Restarting only '$Name'..." -ForegroundColor Cyan
docker compose restart $Name
docker compose ps $Name

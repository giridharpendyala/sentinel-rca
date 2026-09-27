<#
.SYNOPSIS
  Runs one end-to-end incident demo: arms the fault, drives load, runs the
  LangGraph investigator, and cleans up. Requires the stack to already be
  running (scripts\start-all.ps1) and a real OPENAI_API_KEY in .env.
.EXAMPLE
  .\scripts\run-demo.ps1 -Incident INC-01
#>
param(
  [Parameter(Mandatory = $true)]
  [string]$Incident,

  [string]$AgentVersion = $env:AGENT_VERSION
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$pyArgs = @("scripts\run_demo.py", "--incident", $Incident)
if ($AgentVersion) { $pyArgs += @("--agent-version", $AgentVersion) }

& ".\.venv\Scripts\python.exe" @pyArgs
exit $LASTEXITCODE

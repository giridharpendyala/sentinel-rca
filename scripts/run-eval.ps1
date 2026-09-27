<#
.SYNOPSIS
  Runs the automated evaluation harness against the capstone stack.
  Evaluates all 10 incident fixtures or a specific incident ID.
.EXAMPLE
  .\scripts\run-eval.ps1
  .\scripts\run-eval.ps1 -Incident INC-01
  .\scripts\run-eval.ps1 -AgentVersion v2-tuned
#>
param(
  [string]$Incident,
  [string]$AgentVersion = "v1-baseline"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$argsList = @("eval\run_eval.py", "--agent-version", $AgentVersion)
if ($Incident) {
  $argsList += @("--incident", $Incident)
}

& $py @argsList
exit $LASTEXITCODE

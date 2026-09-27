"""Orchestrates one end-to-end incident demo: arms the fault, drives load,
waits for telemetry to accumulate, runs the LangGraph investigator, then
cleans up. Does not import agents/ internals directly - shells out to
`agents.cli` as a subprocess so this script has no coupling to the agent
implementation.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

INCIDENT_CONTROLLER_URL = os.environ.get("INCIDENT_CONTROLLER_URL", "http://localhost:58006")
LOAD_GENERATOR_URL = "http://localhost:58005"


def load_incident(incident_id: str) -> dict:
    path = ROOT / "eval" / "incidents" / f"{incident_id}.yaml"
    if not path.exists():
        print(f"Incident fixture not found: {path}", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one end-to-end incident demo")
    parser.add_argument("--incident", required=True, help="Incident id, e.g. INC-01")
    parser.add_argument("--agent-version", default=os.environ.get("AGENT_VERSION", "v1-baseline"))
    parser.add_argument("--warmup-seconds", type=int, default=None, help="Override the fixture's duration_seconds")
    args = parser.parse_args()

    incident = load_incident(args.incident)
    load_rps = incident.get("load_rps", 15)
    warmup = args.warmup_seconds or incident.get("duration_seconds", 30)

    print(f"=== {args.incident}: {incident.get('alert_text', '').strip()[:100]}...")

    print(f"Starting load generator at {load_rps} rps...")
    httpx.post(f"{LOAD_GENERATOR_URL}/admin/start", json={"rps": load_rps}, timeout=10).raise_for_status()

    fault_type = incident.get("fault", {}).get("type", "none")
    if fault_type != "none":
        print(f"Arming fault on {incident['fault']['service']} ({fault_type})...")
        resp = httpx.post(f"{INCIDENT_CONTROLLER_URL}/control/incidents/{args.incident}/start", timeout=10)
        resp.raise_for_status()
    else:
        print("No fault to arm for this incident (e.g. pure traffic spike).")

    print(f"Warming up for {warmup}s so telemetry accumulates...")
    time.sleep(warmup)

    print("Running the LangGraph investigator (agents.cli)...")
    env = os.environ.copy()
    env["AGENT_VERSION"] = args.agent_version
    result = subprocess.run(
        [str(ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "agents.cli", "--incident", args.incident],
        cwd=str(ROOT),
        env=env,
    )

    print("Cleaning up: stopping load generator and disarming fault...")
    try:
        httpx.post(f"{LOAD_GENERATOR_URL}/admin/stop", timeout=10)
    except httpx.HTTPError:
        pass
    if fault_type != "none":
        try:
            httpx.post(f"{INCIDENT_CONTROLLER_URL}/control/incidents/{args.incident}/stop", timeout=10)
        except httpx.HTTPError:
            pass

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()

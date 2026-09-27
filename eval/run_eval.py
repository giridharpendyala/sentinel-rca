"""Automated evaluation harness for the Multi-Agent Incident Investigator.

Runs all 10 incident scenarios (or a selected subset) against the live stack,
runs the 6 evaluators on each result, tags runs with AGENT_VERSION, and stores
the full scoring report in eval/results/<version>_<timestamp>.json.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from agents.cli import run_investigation
from eval.evaluators import (
    evaluate_efficiency,
    evaluate_evidence_grounding,
    evaluate_hallucination,
    evaluate_investigation_path,
    evaluate_rca_accuracy,
    evaluate_tool_selection,
)

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

INCIDENTS_DIR = _ROOT / "eval" / "incidents"
RESULTS_DIR = _ROOT / "eval" / "results"

INCIDENT_CONTROLLER_URL = os.environ.get("INCIDENT_CONTROLLER_URL", "http://localhost:58006")
LOAD_GENERATOR_URL = "http://localhost:58005"

console = Console()


def arm_incident(fixture: dict) -> None:
    """Start load and arm the fixture's fault, mirroring scripts/run_demo.py.

    Without this, the harness would run the investigator against whatever
    telemetry state happens to already exist instead of the incident it
    claims to be scoring.
    """
    rps = fixture.get("load_rps", 15)
    httpx.post(f"{LOAD_GENERATOR_URL}/admin/start", json={"rps": rps}, timeout=10).raise_for_status()

    fault_type = fixture.get("fault", {}).get("type", "none")
    if fault_type != "none":
        resp = httpx.post(f"{INCIDENT_CONTROLLER_URL}/control/incidents/{fixture['id']}/start", timeout=10)
        resp.raise_for_status()

    warmup = fixture.get("duration_seconds", 30)
    time.sleep(warmup)


def disarm_incident(fixture: dict) -> None:
    fault_type = fixture.get("fault", {}).get("type", "none")
    try:
        httpx.post(f"{LOAD_GENERATOR_URL}/admin/stop", timeout=10)
    except httpx.HTTPError:
        pass
    if fault_type != "none":
        try:
            httpx.post(f"{INCIDENT_CONTROLLER_URL}/control/incidents/{fixture['id']}/stop", timeout=10)
        except httpx.HTTPError:
            pass


def load_all_fixtures() -> list[dict]:
    fixtures = []
    for file in sorted(INCIDENTS_DIR.glob("INC-*.yaml")):
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
        if data:
            fixtures.append(data)
    return fixtures


def evaluate_single_run(
    fixture: dict,
    final_state: dict,
    duration_sec: float,
) -> dict[str, Any]:
    rca = final_state.get("rca")
    rca_obj = rca if isinstance(rca, dict) else (rca.model_dump() if rca else {})

    ground_truth = fixture.get("ground_truth", {})
    gt_rca = ground_truth.get("root_cause", "")
    req_evidence = ground_truth.get("required_evidence", [])
    exp_tools = ground_truth.get("expected_tools", [])

    agent_rca_text = rca_obj.get("root_cause", "")
    cited_evidence = rca_obj.get("evidence", [])
    collected_evidence = final_state.get("evidence", [])
    tool_call_log = final_state.get("tool_call_log", [])
    used_tools = [r.get("agent") for r in tool_call_log if r.get("agent")]
    path = [r.get("agent") for r in tool_call_log]

    # Run the 6 evaluators
    score_accuracy = evaluate_rca_accuracy(agent_rca_text, gt_rca)
    score_grounding = evaluate_evidence_grounding(cited_evidence, collected_evidence, req_evidence)
    score_tools = evaluate_tool_selection(used_tools, exp_tools)
    score_path = evaluate_investigation_path(path)
    score_hallucination = evaluate_hallucination(agent_rca_text, collected_evidence)
    score_efficiency = evaluate_efficiency(final_state.get("iterations", 1), tool_call_log, duration_sec)

    return {
        "incident_id": fixture.get("id"),
        "target_service": fixture.get("target_service"),
        "metrics": {
            "rca_accuracy": score_accuracy["score"],
            "evidence_grounding": score_grounding["score"],
            "tool_selection": score_tools["score"],
            "investigation_path": score_path["score"],
            "hallucination": score_hallucination["score"],
            "efficiency": score_efficiency["score"],
        },
        "details": {
            "accuracy": score_accuracy,
            "grounding": score_grounding,
            "tools": score_tools,
            "path": score_path,
            "hallucination": score_hallucination,
            "efficiency": score_efficiency,
        },
        "duration_seconds": round(duration_sec, 2),
        "trace_url": final_state.get("trace_url"),
    }


def main():
    parser = argparse.ArgumentParser(description="Run Capstone Multi-Agent Evaluation Harness")
    parser.add_argument("--incident", help="Run a specific incident only, e.g. INC-01")
    parser.add_argument("--agent-version", default=os.environ.get("AGENT_VERSION", "v1-baseline"))
    parser.add_argument("--auto-approve", action="store_true", default=True, help="Auto-approve remediation")
    args = parser.parse_args()

    fixtures = load_all_fixtures()
    if args.incident:
        fixtures = [f for f in fixtures if f.get("id") == args.incident]
        if not fixtures:
            console.print(f"[bold red]Error:[/bold red] Incident {args.incident} not found.")
            sys.exit(1)

    console.rule(f"[bold cyan]Running Evaluation Suite ({len(fixtures)} scenarios) | Version: {args.agent_version}[/bold cyan]")

    eval_results = []
    run_timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    for fixture in fixtures:
        inc_id = fixture["id"]
        console.print(f"\n[bold yellow]▶ Evaluating {inc_id} ({fixture.get('target_service')})...[/bold yellow]")

        console.print(f"  [dim]Arming fault + driving load ({fixture.get('load_rps', 15)} rps)...[/dim]")
        arm_incident(fixture)

        t0 = time.perf_counter()
        try:
            final_state = run_investigation(
                incident_id=inc_id,
                alert_text=fixture.get("alert_text", ""),
                affected_service=fixture.get("target_service", "checkout-service"),
                auto_approve=args.auto_approve,
                agent_version=args.agent_version,
                quiet=True,
            )
        finally:
            disarm_incident(fixture)
        duration = time.perf_counter() - t0

        single_res = evaluate_single_run(fixture, final_state, duration)
        eval_results.append(single_res)

        m = single_res["metrics"]
        console.print(
            f"  [green]✓[/green] RCA Acc: {m['rca_accuracy']} | Grounding: {m['evidence_grounding']} | "
            f"Tools: {m['tool_selection']} | Path: {m['investigation_path']} | "
            f"Hallucination: {m['hallucination']} | Time: {single_res['duration_seconds']}s"
        )

    # Calculate overall averages
    avg_accuracy = round(sum(r["metrics"]["rca_accuracy"] for r in eval_results) / len(eval_results), 2)
    avg_grounding = round(sum(r["metrics"]["evidence_grounding"] for r in eval_results) / len(eval_results), 2)
    avg_tools = round(sum(r["metrics"]["tool_selection"] for r in eval_results) / len(eval_results), 2)
    avg_path = round(sum(r["metrics"]["investigation_path"] for r in eval_results) / len(eval_results), 2)
    avg_hallucination = round(sum(r["metrics"]["hallucination"] for r in eval_results) / len(eval_results), 2)
    avg_duration = round(sum(r["duration_seconds"] for r in eval_results) / len(eval_results), 1)

    summary_data = {
        "agent_version": args.agent_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(eval_results),
        "averages": {
            "rca_accuracy": avg_accuracy,
            "evidence_grounding": avg_grounding,
            "tool_selection": avg_tools,
            "investigation_path": avg_path,
            "hallucination": avg_hallucination,
            "avg_duration_seconds": avg_duration,
        },
        "results": eval_results,
    }

    # Save results JSON
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = RESULTS_DIR / f"{args.agent_version}_{run_timestamp}.json"
    out_file.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

    # Display Rich Table
    console.print()
    table = Table(title=f"Evaluation Summary Report: {args.agent_version}", header_style="bold cyan")
    table.add_column("Incident", style="bold yellow")
    table.add_column("RCA Acc", justify="center")
    table.add_column("Grounding", justify="center")
    table.add_column("Tool Sel", justify="center")
    table.add_column("Path", justify="center")
    table.add_column("No-Halluc", justify="center")
    table.add_column("Latency", justify="right")

    for r in eval_results:
        m = r["metrics"]
        table.add_row(
            r["incident_id"],
            f"{int(m['rca_accuracy']*100)}%",
            f"{int(m['evidence_grounding']*100)}%",
            f"{int(m['tool_selection']*100)}%",
            f"{int(m['investigation_path']*100)}%",
            f"{int(m['hallucination']*100)}%",
            f"{r['duration_seconds']}s",
        )

    table.add_section()
    table.add_row(
        "[bold]AVERAGE[/bold]",
        f"[bold green]{int(avg_accuracy*100)}%[/bold green]",
        f"[bold green]{int(avg_grounding*100)}%[/bold green]",
        f"[bold green]{int(avg_tools*100)}%[/bold green]",
        f"[bold green]{int(avg_path*100)}%[/bold green]",
        f"[bold green]{int(avg_hallucination*100)}%[/bold green]",
        f"[bold]{avg_duration}s[/bold]",
    )

    console.print(table)
    console.print(f"\n[green]✓ Results saved to:[/green] [dim]{out_file}[/dim]\n")


if __name__ == "__main__":
    main()

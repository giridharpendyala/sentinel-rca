"""Command-line interface for the LangGraph multi-agent incident investigator.

Executes an incident investigation end-to-end, prints live step-by-step progress,
handles human-in-the-loop remediation approval via LangGraph interrupt(), and
attaches a Langfuse trace callback.
"""

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agents.graph import build_graph
from agents.tracing import flush_langfuse_handler, get_handler_trace_url, get_langfuse_handler
from langgraph.types import Command

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console(highlight=False)


def load_incident_fixture(incident_id: str) -> dict:
    path = _ROOT / "eval" / "incidents" / f"{incident_id}.yaml"
    if not path.exists():
        console.print(f"[bold red]Error:[/bold red] Incident fixture not found: {path}")
        sys.exit(1)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_investigation(
    incident_id: str,
    alert_text: str,
    affected_service: str,
    auto_approve: bool = False,
    agent_version: str = "v1-baseline",
    quiet: bool = False,
) -> dict[str, Any]:
    """Run the multi-agent graph with streaming and interactive approval support."""
    thread_id = f"inv-{incident_id}-{uuid.uuid4().hex[:8]}"

    initial_state = {
        "incident_id": incident_id,
        "alert_text": alert_text.strip(),
        "affected_service": affected_service,
        "time_window": {"minutes_back": 15, "start_iso": datetime.now(timezone.utc).isoformat()},
        "messages": [],
        "evidence": [],
        "tool_call_log": [],
        "hypotheses": [],
        "rca": None,
        "pending_action": None,
        "iterations": 0,
        "errors": [],
    }

    if not quiet:
        console.rule(f"[bold cyan]🔍 Starting Multi-Agent Investigation ({incident_id})[/bold cyan]")
        console.print(f"[bold]Target Service:[/bold] [yellow]{affected_service}[/yellow]")
        console.print(f"[bold]Alert:[/bold] {alert_text.strip()}")
        console.print(f"[bold]Session ID:[/bold] {thread_id} | [bold]Agent Version:[/bold] {agent_version}")
        console.print()

    graph = build_graph()
    langfuse_handler = get_langfuse_handler(tags=[incident_id, agent_version], session_id=thread_id)
    callbacks = [langfuse_handler] if langfuse_handler else []

    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": callbacks,
        "metadata": {
            "langfuse_session_id": thread_id,
            "langfuse_tags": [incident_id, agent_version],
            "langfuse_user_id": "operator",
        },
    }

    step_input: Any = initial_state
    final_state: dict[str, Any] = {}

    while True:
        interrupted = False
        interrupt_payload = None

        for output in graph.stream(step_input, config=config, stream_mode="updates"):
            if isinstance(output, tuple):
                output = output[1] if len(output) > 1 and isinstance(output[1], dict) else {}
            if not isinstance(output, dict):
                continue
            for node_name, node_update in output.items():
                if node_name == "__interrupt__" or not isinstance(node_update, dict):
                    continue
                if not quiet:
                    _display_node_update(node_name, node_update)

        state_snapshot = graph.get_state(config)
        if state_snapshot.values:
            final_state = dict(state_snapshot.values)

        # Check if the graph has paused at an interrupt (e.g. remediation approval)
        if state_snapshot.next and "remediation" in state_snapshot.next:
            interrupted = True
            for task in state_snapshot.tasks:
                if task.interrupts:
                    interrupt_payload = task.interrupts[0].value
                    break

        if not interrupted:
            break

        # Handle human approval gate
        if not quiet and interrupt_payload:
            console.print()
            approval_panel = Panel(
                f"[bold red]⚠️ Human Approval Required for Production Remediation[/bold red]\n\n"
                f"[bold]Action:[/bold] {interrupt_payload.get('action')}\n"
                f"[bold]Target Service:[/bold] {interrupt_payload.get('target_service')}\n"
                f"[bold]Rationale:[/bold] {interrupt_payload.get('rationale')}",
                border_style="red",
                title="[bold yellow]Remediation Gate[/bold yellow]",
            )
            console.print(approval_panel)

        approved = False
        if auto_approve:
            approved = True
            if not quiet:
                console.print("[green]✓ Auto-approve enabled: Action approved by policy.[/green]")
        else:
            try:
                response = input("Do you approve applying this remediation? [y/N]: ").strip().lower()
                approved = response in ("y", "yes")
            except (EOFError, KeyboardInterrupt):
                approved = False

            if approved:
                console.print("[green]✓ Action APPROVED by operator.[/green]")
            else:
                console.print("[yellow]✕ Action REJECTED by operator.[/yellow]")

        # Resume execution with operator decision
        step_input = Command(resume={"approved": approved})

    # Summary Display
    flush_langfuse_handler(langfuse_handler)
    trace_url = get_handler_trace_url(langfuse_handler)
    if not quiet:
        _display_final_summary(final_state, trace_url)

    final_state["trace_url"] = trace_url
    return final_state


def _display_node_update(node_name: str, update: dict) -> None:
    if node_name == "supervisor":
        hypotheses = update.get("hypotheses", [])
        last_h = hypotheses[-1] if hypotheses else ""
        action = update.get("pending_action", {}).get("next", "continue")
        console.print(f"[bold magenta]▶ [Supervisor][/bold magenta] Step {update.get('iterations', 1)} → Route: [cyan]{action}[/cyan]")
        if last_h:
            console.print(f"   [dim]{last_h}[/dim]")
    elif node_name in ("metrics", "traces", "logs", "changes"):
        evidence = update.get("evidence", [])
        if evidence:
            last_e = evidence[-1]
            console.print(f"[bold green]✓ [{node_name.capitalize()} Agent][/bold green] Telemetry gathered:")
            console.print(f"   [dim]{last_e.get('summary')}[/dim]")
    elif node_name == "rca_agent":
        console.print("[bold yellow]★ [RCA Agent][/bold yellow] Root cause analysis synthesized.")
    elif node_name == "remediation":
        errors = update.get("errors", [])
        if errors:
            console.print(f"[bold blue]ℹ [Remediation][/bold blue] {errors[-1]}")


def _display_final_summary(state: dict, trace_url: Optional[str]) -> None:
    rca = state.get("rca")
    if not rca:
        console.print("[bold red]No RCA was produced by the investigation.[/bold red]")
        return

    console.print()
    console.rule("[bold green]Incident Investigation Report[/bold green]")

    rca_obj = rca if isinstance(rca, dict) else rca.model_dump()

    conf_color = "green" if rca_obj.get("confidence") == "high" else "yellow"
    content = (
        f"[bold]Root Cause:[/bold]\n{rca_obj.get('root_cause')}\n\n"
        f"[bold]Confidence:[/bold] [{conf_color}]{rca_obj.get('confidence', '').upper()}[/{conf_color}]\n\n"
        f"[bold]Recommended Action:[/bold]\n{rca_obj.get('recommended_action')}\n\n"
        f"[bold]Requires Approval:[/bold] {rca_obj.get('requires_approval')}"
    )

    console.print(Panel(content, title="[bold cyan]Root Cause Analysis[/bold cyan]", border_style="cyan"))

    evidence_list = rca_obj.get("evidence", [])
    if evidence_list:
        table = Table(title="Supporting Telemetry Evidence", show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("Evidence Cited", style="white")
        for i, ev in enumerate(evidence_list, start=1):
            table.add_row(str(i), str(ev))
        console.print(table)

    if trace_url:
        console.print()
        console.print(
            Panel(
                f"Langfuse Trace URL:\n[bold underline blue]{trace_url}[/bold underline blue]\n\n"
                f"Metrics / Dashboards:\n"
                f"• Grafana: http://localhost:53300\n"
                f"• Prometheus: http://localhost:59090",
                title="[bold green]AgentOps Observability[/bold green]",
                border_style="green",
            )
        )
    console.print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Agent Incident Investigator CLI")
    parser.add_argument("--incident", help="Incident ID from eval/incidents, e.g. INC-01")
    parser.add_argument("--alert", help="Custom alert message")
    parser.add_argument("--service", help="Affected service name", default=None)
    parser.add_argument("--auto-approve", action="store_true", help="Auto-approve remediation actions")
    parser.add_argument("--agent-version", default=os.environ.get("AGENT_VERSION", "v1-baseline"))
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose terminal output")

    args = parser.parse_args()

    if not args.incident and not args.alert:
        parser.error("Either --incident or --alert must be provided.")

    if args.incident:
        fixture = load_incident_fixture(args.incident)
        alert_text = fixture.get("alert_text", "")
        affected_service = args.service or fixture.get("target_service", "checkout-service")
        incident_id = args.incident
    else:
        incident_id = f"MANUAL-{uuid.uuid4().hex[:6].upper()}"
        alert_text = args.alert
        affected_service = args.service or "checkout-service"

    run_investigation(
        incident_id=incident_id,
        alert_text=alert_text,
        affected_service=affected_service,
        auto_approve=args.auto_approve,
        agent_version=args.agent_version,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    main()

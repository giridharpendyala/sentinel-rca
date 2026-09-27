"""Compare two evaluation runs to demonstrate AgentOps regression & improvement.

Usage:
  python eval/compare_runs.py v1-baseline v2-tuned
"""

import argparse
import json
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table

_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = _ROOT / "eval" / "results"

console = Console()


def find_latest_result_file(version_pattern: str) -> Path:
    matches = list(RESULTS_DIR.glob(f"{version_pattern}*.json"))
    if not matches:
        console.print(f"[bold red]Error:[/bold red] No result file found for version pattern '{version_pattern}' in {RESULTS_DIR}")
        sys.exit(1)
    # Return latest modified
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def main():
    parser = argparse.ArgumentParser(description="Compare two agent evaluation runs (regression tracking)")
    parser.add_argument("baseline", help="Baseline version tag or result file, e.g. v1-baseline")
    parser.add_argument("candidate", help="Candidate version tag or result file, e.g. v2-tuned")
    args = parser.parse_args()

    baseline_path = Path(args.baseline) if Path(args.baseline).exists() else find_latest_result_file(args.baseline)
    candidate_path = Path(args.candidate) if Path(args.candidate).exists() else find_latest_result_file(args.candidate)

    baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    candidate_data = json.loads(candidate_path.read_text(encoding="utf-8"))

    b_avg = baseline_data.get("averages", {})
    c_avg = candidate_data.get("averages", {})

    b_ver = baseline_data.get("agent_version", args.baseline)
    c_ver = candidate_data.get("agent_version", args.candidate)

    console.rule(f"[bold cyan]AgentOps Regression Analysis: {b_ver} vs {c_ver}[/bold cyan]")
    console.print(f"Baseline file:  [dim]{baseline_path.name}[/dim]")
    console.print(f"Candidate file: [dim]{candidate_path.name}[/dim]\n")

    table = Table(title="Performance & Accuracy Comparison", header_style="bold magenta")
    table.add_column("Metric", style="bold")
    table.add_column(f"{b_ver} (Baseline)", justify="center")
    table.add_column(f"{c_ver} (Candidate)", justify="center")
    table.add_column("Delta", justify="center")

    metrics_def = [
        ("RCA Accuracy", "rca_accuracy", True),
        ("Evidence Grounding", "evidence_grounding", True),
        ("Tool Selection F1", "tool_selection", True),
        ("Investigation Path", "investigation_path", True),
        ("Hallucination Resistance", "hallucination", True),
        ("Avg Latency (seconds)", "avg_duration_seconds", False),
    ]

    for label, key, higher_is_better in metrics_def:
        b_val = b_avg.get(key, 0)
        c_val = c_avg.get(key, 0)
        diff = c_val - b_val

        if key.endswith("seconds"):
            b_str = f"{b_val:.1f}s"
            c_str = f"{c_val:.1f}s"
            diff_str = f"{diff:+.1f}s"
            improved = diff < 0
        else:
            b_str = f"{int(b_val * 100)}%"
            c_str = f"{int(c_val * 100)}%"
            diff_str = f"{int(diff * 100):+d}%"
            improved = diff > 0

        diff_color = "green" if improved else ("red" if diff != 0 else "dim")
        table.add_row(label, b_str, c_str, f"[{diff_color}]{diff_str}[/{diff_color}]")

    console.print(table)
    console.print()


if __name__ == "__main__":
    main()

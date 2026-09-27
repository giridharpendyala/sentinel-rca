from typing import Any


def evaluate_efficiency(
    iterations: int,
    tool_call_log: list[dict],
    duration_seconds: float,
) -> dict[str, Any]:
    """Calculate efficiency metrics (tool call count, latency, estimated tokens)."""
    total_tool_calls = len(tool_call_log)
    total_tool_time_ms = sum(r.get("latency_ms", 0) for r in tool_call_log)

    # Efficiency score: normalized 0.0 - 1.0 (penalizing high latency and excessive tool calls)
    latency_penalty = max(0.0, min(0.5, (duration_seconds - 15) / 60))
    calls_penalty = max(0.0, min(0.5, (total_tool_calls - 4) / 20))
    score = max(0.1, round(1.0 - (latency_penalty + calls_penalty), 2))

    return {
        "score": score,
        "iterations": iterations,
        "total_tool_calls": total_tool_calls,
        "duration_seconds": round(duration_seconds, 2),
        "total_tool_time_ms": round(total_tool_time_ms, 2),
        "reasoning": f"Investigation finished in {round(duration_seconds, 1)}s with {total_tool_calls} tool calls over {iterations} iterations.",
    }

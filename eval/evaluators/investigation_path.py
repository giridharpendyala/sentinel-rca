from typing import Any


def evaluate_investigation_path(
    path: list[str],
    max_iterations: int = 8,
) -> dict[str, Any]:
    """Score whether the supervisor followed a logical, non-repetitive investigation path."""
    if not path:
        return {"score": 0.0, "reasoning": "Investigation path was empty."}

    penalties = 0.0

    # 1. Did it exceed max iterations?
    if len(path) > max_iterations:
        penalties += 0.3

    # 2. Did it loop repeatedly on the exact same node consecutively?
    consecutive_repeats = sum(1 for i in range(len(path) - 1) if path[i] == path[i + 1])
    if consecutive_repeats > 0:
        penalties += min(0.4, consecutive_repeats * 0.2)

    # 3. Best practice: check telemetry (metrics/traces/logs) before jumping to changes
    if "changes" in path:
        changes_idx = path.index("changes")
        has_preceding_telemetry = any(p in ("metrics", "traces", "logs") for p in path[:changes_idx])
        if not has_preceding_telemetry and len(path) > 1:
            penalties += 0.2

    score = max(0.0, round(1.0 - penalties, 2))
    return {
        "score": score,
        "path_length": len(path),
        "path": path,
        "consecutive_repeats": consecutive_repeats,
        "reasoning": f"Path of length {len(path)} with {consecutive_repeats} consecutive repeats.",
    }

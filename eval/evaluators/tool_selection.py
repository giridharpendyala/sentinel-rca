from typing import Any


def evaluate_tool_selection(
    used_tools: list[str],
    expected_tools: list[str],
) -> dict[str, Any]:
    """Score whether agents queried appropriate telemetry tools."""
    used_set = set(used_tools)
    expected_set = set(expected_tools)

    if not expected_set:
        return {"score": 1.0, "reasoning": "No expected tools specified."}

    overlap = used_set.intersection(expected_set)
    precision = len(overlap) / max(1, len(used_set))
    recall = len(overlap) / len(expected_set)

    # F1 score as the overall tool selection score
    f1 = 0.0
    if precision + recall > 0:
        f1 = (2 * precision * recall) / (precision + recall)

    return {
        "score": round(f1, 2),
        "precision": round(precision, 2),
        "recall": round(recall, 2),
        "used": list(used_set),
        "expected": list(expected_set),
        "missing": list(expected_set - used_set),
        "reasoning": f"Queried {len(overlap)} of {len(expected_set)} expected tools.",
    }

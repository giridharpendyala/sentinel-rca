import re
from typing import Any


def evaluate_hallucination(
    agent_rca: str,
    collected_evidence: list[dict],
) -> dict[str, Any]:
    """Score hallucination risk (1.0 = no hallucination, 0.0 = severe hallucination)."""
    if not agent_rca:
        return {"score": 1.0, "reasoning": "No claims made in RCA."}

    all_raw = " ".join(f"{e.get('summary', '')} {e.get('query', '')}" for e in collected_evidence).lower()

    # Extract specific numbers, percentages, and service identifiers claimed in RCA
    numeric_claims = re.findall(r"\b\d+(?:\.\d+)?%?\b", agent_rca)
    unsupported_numbers = []

    for num in numeric_claims:
        if len(num) > 1 and num not in all_raw:
            unsupported_numbers.append(num)

    if not numeric_claims:
        score = 1.0
    else:
        unsupported_ratio = len(unsupported_numbers) / len(numeric_claims)
        score = max(0.0, round(1.0 - unsupported_ratio, 2))

    return {
        "score": score,
        "unsupported_claims_count": len(unsupported_numbers),
        "unsupported_examples": unsupported_numbers[:3],
        "reasoning": f"{len(unsupported_numbers)} unsupported numeric claims detected in RCA.",
    }

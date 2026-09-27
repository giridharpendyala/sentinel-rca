from typing import Any


def evaluate_evidence_grounding(
    cited_evidence: list[str],
    collected_evidence: list[dict],
    required_evidence: list[str],
) -> dict[str, Any]:
    """Score whether cited evidence is grounded in telemetry and satisfies required evidence."""
    if not cited_evidence:
        return {"score": 0.0, "reasoning": "No evidence was cited in the RCA."}

    all_telemetry_text = " ".join(
        f"{e.get('summary', '')} {e.get('query', '')}" for e in collected_evidence
    ).lower()

    grounded_count = 0
    for item in cited_evidence:
        # Check if key tokens from the citation appear in the collected telemetry
        tokens = [t.lower() for t in item.split() if len(t) > 3]
        if not tokens:
            continue
        matches = sum(1 for t in tokens if t in all_telemetry_text)
        if matches / len(tokens) >= 0.3:
            grounded_count += 1

    citation_grounding_rate = grounded_count / max(1, len(cited_evidence))

    # Required evidence coverage
    covered_required = 0
    for req in required_evidence:
        req_tokens = [t.lower() for t in req.split() if len(t) > 3]
        if any(t in all_telemetry_text for t in req_tokens):
            covered_required += 1

    coverage_rate = covered_required / max(1, len(required_evidence))

    final_score = round((citation_grounding_rate * 0.5) + (coverage_rate * 0.5), 2)
    return {
        "score": final_score,
        "citation_grounding_rate": round(citation_grounding_rate, 2),
        "required_coverage_rate": round(coverage_rate, 2),
        "reasoning": f"{grounded_count}/{len(cited_evidence)} citations grounded; {covered_required}/{len(required_evidence)} required facts covered.",
    }

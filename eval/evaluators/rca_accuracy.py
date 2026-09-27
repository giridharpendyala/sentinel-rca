import os
from typing import Any
from agents.llm import _get_api_key

JUDGE_PROMPT = """You are an expert SRE evaluator judging the root-cause accuracy of an incident investigation.

Ground Truth Root Cause:
{ground_truth}

Agent Synthesized Root Cause:
{agent_rca}

Rate the accuracy on a scale of 0.0 to 1.0:
- 1.0: Identifies the exact same primary root cause and service.
- 0.7 - 0.9: Identifies the correct affected service and primary mechanism, with minor difference in detail.
- 0.4 - 0.6: Identifies the symptom or an upstream effect, but misses the true root cause.
- 0.0 - 0.3: Incorrect service or incorrect root cause.

Respond with ONLY a JSON object: {{"score": float, "reasoning": str}}
"""


def evaluate_rca_accuracy(agent_rca: str, ground_truth: str) -> dict[str, Any]:
    """Score root cause accuracy against ground truth."""
    if not agent_rca:
        return {"score": 0.0, "reasoning": "No RCA was produced"}

    api_key = _get_api_key()
    if api_key and not api_key.startswith("sk-placeholder"):
        try:
            from langchain_openai import ChatOpenAI
            from pydantic import BaseModel

            class JudgeOutput(BaseModel):
                score: float
                reasoning: str

            llm = ChatOpenAI(
                model=os.environ.get("OPENAI_MODEL_JUDGE", "gpt-4o-mini"),
                temperature=0.0,
                api_key=api_key,
            ).with_structured_output(JudgeOutput)

            result: JudgeOutput = llm.invoke(
                JUDGE_PROMPT.format(ground_truth=ground_truth, agent_rca=agent_rca)
            )
            return {"score": round(result.score, 2), "reasoning": result.reasoning}
        except Exception as exc:
            # Fall back to heuristic scoring if judge call fails
            pass

    # Heuristic fallback: keyword overlap matching
    gt_words = set(ground_truth.lower().split())
    agent_words = set(agent_rca.lower().split())
    intersection = gt_words.intersection(agent_words)
    score = min(1.0, round(len(intersection) / max(1, len(gt_words) * 0.4), 2))
    return {
        "score": score,
        "reasoning": f"Heuristic overlap matching ({len(intersection)} shared key terms).",
    }

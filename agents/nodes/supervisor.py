from typing import Literal

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from agents.llm import get_supervisor_llm
from agents.state import InvestigationState

MAX_ITERATIONS = 8


class SupervisorDecision(BaseModel):
    next: Literal["metrics", "traces", "logs", "changes", "rca", "done"]
    rationale: str


_llm = get_supervisor_llm().with_structured_output(SupervisorDecision)

SYSTEM_PROMPT = (
    "You are the Supervisor Agent coordinating an incident investigation. "
    "Incident {incident_id} affecting {affected_service}. Alert: {alert_text}\n\n"
    "Evidence gathered so far:\n{evidence_summary}\n\n"
    "Decide the single next best action: 'metrics', 'traces', 'logs', 'changes' "
    "(to gather more evidence from that source), 'rca' (you have enough evidence "
    "to determine a root cause), or 'done' (no RCA is warranted). "
    "Do not repeat a source that has already given you a clear, conclusive answer. "
    "Check metrics, traces, or logs first to establish the symptom, but ALWAYS check "
    "'changes' before concluding 'rca' to see if a recent deployment or configuration "
    "change caused or triggered the issue. Move to 'rca' once you have gathered telemetry "
    "and checked recent changes."
)


def _evidence_summary(state: InvestigationState) -> str:
    if not state["evidence"]:
        return "(none yet)"
    return "\n".join(f"- [{e['source']}] {e['summary']}" for e in state["evidence"])


def supervisor_node(state: InvestigationState, config: RunnableConfig) -> dict:
    iterations = state["iterations"] + 1

    if iterations > MAX_ITERATIONS:
        return {"iterations": iterations, "hypotheses": state["hypotheses"] + ["max iterations reached, forcing RCA"]}

    prompt = SYSTEM_PROMPT.format(
        incident_id=state["incident_id"],
        affected_service=state["affected_service"],
        alert_text=state["alert_text"],
        evidence_summary=_evidence_summary(state),
    )
    decision: SupervisorDecision = _llm.invoke(prompt, config=config)

    return {
        "iterations": iterations,
        "hypotheses": state["hypotheses"] + [f"{decision.next}: {decision.rationale}"],
        "pending_action": {"next": decision.next},
    }


def route_from_supervisor(state: InvestigationState) -> str:
    if state["iterations"] > MAX_ITERATIONS:
        return "rca"
    return state["pending_action"]["next"]

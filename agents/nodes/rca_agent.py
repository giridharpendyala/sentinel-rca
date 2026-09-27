from langchain_core.runnables import RunnableConfig

from agents.llm import get_rca_llm
from agents.state import InvestigationState, RCAResult

_llm = get_rca_llm().with_structured_output(RCAResult)

PROMPT = (
    "You are the RCA Agent. Correlate the evidence below for incident {incident_id} "
    "affecting {affected_service} and determine the probable root cause.\n\n"
    "Alert: {alert_text}\n\n"
    "Evidence collected by the investigation:\n{evidence_block}\n\n"
    "Your root cause and evidence list MUST be grounded only in the evidence "
    "above -- do not state anything as fact that isn't supported by it. If the "
    "evidence is inconclusive, say so and use 'low' confidence. Set "
    "requires_approval=true only if recommended_action would change a "
    "production system (e.g. restart a service, change a config value, roll "
    "back a deployment); set it false for pure escalation/investigation "
    "recommendations that don't change anything."
)


def _evidence_block(state: InvestigationState) -> str:
    if not state["evidence"]:
        return "(no evidence was collected)"
    return "\n\n".join(f"[{e['source']}] query: {e['query']}\nfindings: {e['summary']}" for e in state["evidence"])


def rca_agent_node(state: InvestigationState, config: RunnableConfig) -> dict:
    prompt = PROMPT.format(
        incident_id=state["incident_id"],
        affected_service=state["affected_service"],
        alert_text=state["alert_text"],
        evidence_block=_evidence_block(state),
    )
    rca: RCAResult = _llm.invoke(prompt, config=config)
    return {"rca": rca}


def route_from_rca(state: InvestigationState) -> str:
    return "remediation" if state["rca"].requires_approval else "done"

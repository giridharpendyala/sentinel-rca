from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from agents.llm import get_specialist_llm
from agents.nodes._common import run_specialist
from agents.state import InvestigationState
from agents.tools.traces_tool import search_traces

_agent = create_react_agent(get_specialist_llm(), tools=[search_traces])

PROMPT = (
    "You are the Trace Agent investigating incident {incident_id} affecting "
    "{affected_service}. Alert: {alert_text}\n"
    "Use search_traces to find slow traces rooted at checkout-service first "
    "(try min_duration_ms=500 or higher), then narrow down which downstream "
    "service (cart-service, pricing-service, payment-service) is responsible "
    "for most of the latency by searching each of them too. "
    "Summarize which service dominates the slow traces and by how much."
)


def trace_agent_node(state: InvestigationState, config: RunnableConfig) -> dict:
    prompt = PROMPT.format(
        incident_id=state["incident_id"],
        affected_service=state["affected_service"],
        alert_text=state["alert_text"],
    )
    return run_specialist(
        _agent, prompt, state, source="traces", agent_name="traces", tool_name="search_traces", config=config
    )

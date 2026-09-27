from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from agents.llm import get_specialist_llm
from agents.nodes._common import run_specialist
from agents.state import InvestigationState
from agents.tools.logs_tool import search_logs

_agent = create_react_agent(get_specialist_llm(), tools=[search_logs])

PROMPT = (
    "You are the Log Agent investigating incident {incident_id} affecting "
    "{affected_service}. Alert: {alert_text}\n"
    "Use search_logs on {affected_service} to look for WARNING/ERROR lines "
    "(e.g. filter_text='Timeout', 'ERROR', 'Lock wait', 'exceeded'). If nothing "
    "relevant turns up, also check checkout-service, cart-service, and "
    "pricing-service. Quote the most relevant log lines verbatim in your summary."
)


def log_agent_node(state: InvestigationState, config: RunnableConfig) -> dict:
    prompt = PROMPT.format(
        incident_id=state["incident_id"],
        affected_service=state["affected_service"],
        alert_text=state["alert_text"],
    )
    return run_specialist(
        _agent, prompt, state, source="logs", agent_name="logs", tool_name="search_logs", config=config
    )

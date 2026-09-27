from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from agents.llm import get_specialist_llm
from agents.nodes._common import run_specialist
from agents.state import InvestigationState
from agents.tools.changes_tool import get_recent_changes

_agent = create_react_agent(get_specialist_llm(), tools=[get_recent_changes])

PROMPT = (
    "You are the Change Agent investigating incident {incident_id} affecting "
    "{affected_service}. Alert: {alert_text}\n"
    "Use get_recent_changes to check for recent deployments or configuration "
    "changes on {affected_service}, and also check with no service filter to "
    "see changes across all services. If there are none, say so explicitly -- "
    "do not invent a change that isn't in the tool's output."
)


def change_agent_node(state: InvestigationState, config: RunnableConfig) -> dict:
    prompt = PROMPT.format(
        incident_id=state["incident_id"],
        affected_service=state["affected_service"],
        alert_text=state["alert_text"],
    )
    return run_specialist(
        _agent, prompt, state, source="changes", agent_name="changes", tool_name="get_recent_changes", config=config
    )

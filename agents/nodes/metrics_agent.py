from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from agents.llm import get_specialist_llm
from agents.nodes._common import run_specialist
from agents.state import InvestigationState
from agents.tools.metrics_tool import query_metrics

_agent = create_react_agent(get_specialist_llm(), tools=[query_metrics])

PROMPT = (
    "You are the Metrics Agent investigating incident {incident_id} affecting "
    "{affected_service}. Alert: {alert_text}\n"
    "Use query_metrics to check latency (p95 via histogram_quantile on "
    "http_request_duration_seconds_bucket), error rate (http_requests_total), "
    "request rate, and any relevant gauges (payment_db_pool_active/size, "
    "process_cpu_seconds_total, process_resident_memory_bytes, "
    "service_restarts_total) for {affected_service} and its neighbors "
    "(checkout-service, cart-service, pricing-service, payment-service). "
    "Summarize what you found in 2-4 sentences citing actual numbers."
)


def metrics_agent_node(state: InvestigationState, config: RunnableConfig) -> dict:
    prompt = PROMPT.format(
        incident_id=state["incident_id"],
        affected_service=state["affected_service"],
        alert_text=state["alert_text"],
    )
    return run_specialist(
        _agent, prompt, state, source="metrics", agent_name="metrics", tool_name="query_metrics", config=config
    )

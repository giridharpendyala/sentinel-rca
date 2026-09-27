import time
from datetime import datetime, timezone

from langchain_core.runnables import RunnableConfig

from agents.state import InvestigationState


def run_specialist(
    agent,
    prompt: str,
    state: InvestigationState,
    source: str,
    agent_name: str,
    tool_name: str,
    config: RunnableConfig,
) -> dict:
    """Invoke a create_react_agent specialist and fold its result into state."""
    start = time.perf_counter()
    # Merge the incoming config (carries the Langfuse callback) with our own
    # recursion_limit, instead of replacing it -- otherwise every LLM call made
    # by this specialist is invisible to Langfuse (no callbacks propagated).
    child_config = {**(config or {}), "recursion_limit": 10}
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]}, config=child_config)
    elapsed_ms = (time.perf_counter() - start) * 1000

    summary = result["messages"][-1].content
    tool_call_count = sum(len(getattr(m, "tool_calls", None) or []) for m in result["messages"])

    evidence = {
        "source": source,
        "query": prompt,
        "summary": summary,
        "raw_ref": f"{source}:{state['affected_service']}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    tool_call_record = {
        "agent": agent_name,
        "tool": tool_name,
        "args": {"calls": tool_call_count},
        "latency_ms": elapsed_ms,
        "tokens": None,
    }
    return {
        "evidence": state["evidence"] + [evidence],
        "tool_call_log": state["tool_call_log"] + [tool_call_record],
    }

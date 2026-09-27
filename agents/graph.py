from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.nodes.change_agent import change_agent_node
from agents.nodes.log_agent import log_agent_node
from agents.nodes.metrics_agent import metrics_agent_node
from agents.nodes.rca_agent import rca_agent_node, route_from_rca
from agents.nodes.remediation import remediation_node
from agents.nodes.supervisor import route_from_supervisor, supervisor_node
from agents.nodes.trace_agent import trace_agent_node
from agents.state import InvestigationState


def build_graph():
    graph = StateGraph(InvestigationState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("metrics", metrics_agent_node)
    graph.add_node("traces", trace_agent_node)
    graph.add_node("logs", log_agent_node)
    graph.add_node("changes", change_agent_node)
    graph.add_node("rca_agent", rca_agent_node)
    graph.add_node("remediation", remediation_node)

    graph.set_entry_point("supervisor")

    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "metrics": "metrics",
            "traces": "traces",
            "logs": "logs",
            "changes": "changes",
            "rca": "rca_agent",
            "done": END,
        },
    )
    for specialist in ("metrics", "traces", "logs", "changes"):
        graph.add_edge(specialist, "supervisor")

    graph.add_conditional_edges("rca_agent", route_from_rca, {"remediation": "remediation", "done": END})
    graph.add_edge("remediation", END)

    return graph.compile(checkpointer=MemorySaver())

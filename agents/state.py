from typing import Annotated, Literal, Optional, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel


class Evidence(TypedDict):
    source: Literal["metrics", "traces", "logs", "changes"]
    query: str
    summary: str
    raw_ref: str
    timestamp: str


class ToolCallRecord(TypedDict):
    agent: str
    tool: str
    args: dict
    latency_ms: float
    tokens: Optional[int]


class RCAResult(BaseModel):
    root_cause: str
    confidence: Literal["low", "medium", "high"]
    evidence: list[str]
    recommended_action: str
    requires_approval: bool


class InvestigationState(TypedDict):
    incident_id: str
    alert_text: str
    affected_service: str
    time_window: dict
    messages: Annotated[list, add_messages]
    evidence: list[Evidence]
    tool_call_log: list[ToolCallRecord]
    hypotheses: list[str]
    rca: Optional[RCAResult]
    pending_action: Optional[dict]
    iterations: int
    errors: list[str]

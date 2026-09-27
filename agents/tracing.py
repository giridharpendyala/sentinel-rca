import os
from typing import Optional

from langfuse import Langfuse
from langfuse.langchain import CallbackHandler


class SessionCallbackHandler(CallbackHandler):
    """Custom CallbackHandler that guarantees session_id and tags are attached to traces."""

    def __init__(self, session_id: Optional[str] = None, tags: Optional[list[str]] = None, **kwargs):
        super().__init__(**kwargs)
        self.default_session_id = session_id
        self.default_tags = tags or []

    def _parse_langfuse_trace_attributes_from_metadata(self, metadata):
        attrs = super()._parse_langfuse_trace_attributes_from_metadata(metadata)
        if "session_id" not in attrs and self.default_session_id:
            attrs["session_id"] = self.default_session_id
        if "tags" not in attrs and self.default_tags:
            attrs["tags"] = [str(t) for t in self.default_tags]
        return attrs


def get_langfuse_handler(
    tags: Optional[list[str]] = None,
    session_id: Optional[str] = None,
) -> Optional[CallbackHandler]:
    """Instantiate a Langfuse LangChain callback handler with proper project configuration.

    A LangGraph investigation makes several separate graph.stream() calls (one per
    segment between human-approval interrupts). Each such call would otherwise start
    its own, disconnected Langfuse trace. Deriving a fixed trace id from session_id
    (stable across every segment of the same investigation) keeps the whole thing --
    supervisor, every specialist, RCA, and remediation -- as one continuous trace.
    """
    try:
        trace_context = None
        if session_id:
            trace_context = {"trace_id": Langfuse.create_trace_id(seed=session_id)}
        handler = SessionCallbackHandler(session_id=session_id, tags=tags, trace_context=trace_context)
        return handler
    except Exception as exc:
        print(f"[tracing] Warning: Failed to initialize Langfuse callback handler: {exc}")
        return None


def flush_langfuse_handler(handler: Optional[CallbackHandler]) -> None:
    """Explicitly flush pending spans to the Langfuse backend."""
    if not handler:
        return
    try:
        client = getattr(handler, "client", None)
        if client and hasattr(client, "flush"):
            client.flush()
    except Exception as exc:
        print(f"[tracing] Warning: Failed to flush Langfuse spans: {exc}")


def trace_url(trace_id: str) -> str:
    """Return the direct clickable URL to a trace in the Langfuse web UI."""
    host = os.environ.get("LANGFUSE_HOST", "http://localhost:54000").rstrip("/")
    project_id = os.environ.get("LANGFUSE_INIT_PROJECT_ID", "capstone-project")
    return f"{host}/project/{project_id}/traces/{trace_id}"


def get_handler_trace_url(handler: Optional[CallbackHandler]) -> Optional[str]:
    """Helper to extract trace URL from a completed handler instance."""
    if not handler:
        return None
    trace_id = getattr(handler, "last_trace_id", None)
    if trace_id:
        return trace_url(str(trace_id))
    return None

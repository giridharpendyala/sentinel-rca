"""Read-only Tempo access for the Trace Agent. GET requests only."""

import os

import httpx
from langchain_core.tools import tool

TEMPO_URL = os.environ.get("TEMPO_URL", "http://localhost:53201")


@tool
def search_traces(service: str, min_duration_ms: int = 0) -> str:
    """Search Tempo for recent traces rooted at the given service.

    Set min_duration_ms to filter for slow traces (e.g. 1000 to find traces
    slower than 1s). Returns the slowest matching traces with their root
    service, root operation name, and duration in ms, sorted slowest-first.
    """
    params: dict = {"tags": f"service.name={service}", "limit": 20}
    if min_duration_ms > 0:
        params["minDuration"] = f"{min_duration_ms}ms"

    try:
        resp = httpx.get(f"{TEMPO_URL}/api/search", params=params, timeout=10.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        return f"error querying Tempo: {exc}"

    traces = resp.json().get("traces", [])
    if not traces:
        return f"no traces found for service={service} (min_duration_ms={min_duration_ms})"

    traces.sort(key=lambda t: int(t.get("durationMs", 0)), reverse=True)
    lines = [
        f"traceID={t['traceID']} root={t.get('rootServiceName')} "
        f"op={t.get('rootTraceName')} durationMs={t.get('durationMs')}"
        for t in traces[:10]
    ]
    return "\n".join(lines)

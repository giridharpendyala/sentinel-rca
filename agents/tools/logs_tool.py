"""Read-only Loki access for the Log Agent. GET requests only.

Every returned log line is passed through masking.mask_text() before it reaches
the LLM or state — this is the enforcement point for the "mask sensitive log
information" enterprise requirement.
"""

import os
import time

import httpx
from langchain_core.tools import tool

from agents.masking import mask_text

LOKI_URL = os.environ.get("LOKI_URL", "http://localhost:53100")


@tool
def search_logs(service: str, minutes_back: int = 15, filter_text: str = "") -> str:
    """Search Loki logs for the given service over the last N minutes.

    Optionally pass filter_text to only include lines containing that substring
    (e.g. "Timeout" or "ERROR"). Sensitive fields (emails, card numbers, tokens)
    are redacted before being returned. Returns up to 30 matching log lines.
    """
    now_ns = time.time_ns()
    start_ns = now_ns - minutes_back * 60 * 1_000_000_000

    logql = f'{{service="{service}"}}'
    if filter_text:
        escaped = filter_text.replace('"', '\\"')
        logql += f' |= "{escaped}"'

    try:
        resp = httpx.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={"query": logql, "start": start_ns, "end": now_ns, "limit": 30, "direction": "backward"},
            timeout=10.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        return f"error querying Loki: {exc}"

    data = resp.json()
    if data.get("status") != "success":
        return f"Loki query failed: {data}"

    lines: list[str] = []
    for stream in data.get("data", {}).get("result", []):
        for _, log_line in stream.get("values", []):
            lines.append(mask_text(log_line))

    if not lines:
        return f"no log lines found for service={service} (filter_text={filter_text!r})"
    return "\n".join(lines[:30])

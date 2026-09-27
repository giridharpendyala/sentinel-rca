"""Read-only Prometheus access for the Metrics Agent. GET requests only."""

import os
import time

import httpx
from langchain_core.tools import tool

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:59090")


def _summarize_range_result(data: dict) -> str:
    result = data.get("data", {}).get("result", [])
    if not result:
        return "no data returned for this query"

    lines = []
    for series in result[:10]:
        labels = series.get("metric", {})
        label_str = ",".join(f"{k}={v}" for k, v in labels.items()) or "(no labels)"
        values = series.get("values", [])
        if not values:
            continue
        nums = [float(v[1]) for v in values]
        last_val = nums[-1]
        lines.append(
            f"{label_str}: last={last_val:.4g} min={min(nums):.4g} max={max(nums):.4g} "
            f"samples={len(nums)}"
        )
    return "\n".join(lines) if lines else "no data returned for this query"


@tool
def query_metrics(promql_query: str, minutes_back: int = 15) -> str:
    """Query Prometheus with a PromQL expression over the last N minutes.

    Use this to check request latency (histogram_quantile over
    http_request_duration_seconds_bucket), error rate (http_requests_total with
    status=~"5.."), request rate, payment_db_pool_active/payment_db_pool_size,
    service_restarts_total, or per-service process metrics like
    process_cpu_seconds_total / process_resident_memory_bytes. Returns a compact
    summary (last/min/max per series), not raw JSON.
    """
    now = time.time()
    start = now - minutes_back * 60
    try:
        resp = httpx.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={"query": promql_query, "start": start, "end": now, "step": "15s"},
            timeout=10.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        return f"error querying Prometheus: {exc}"

    data = resp.json()
    if data.get("status") != "success":
        return f"Prometheus query failed: {data}"
    return _summarize_range_result(data)

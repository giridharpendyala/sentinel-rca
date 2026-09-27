"""Read-only change-log access for the Change Agent. GET requests only.

Only ever calls incident-controller's read-only /control/changes endpoint. Never
calls /control/incidents/*/start|stop or any service's /admin/fault — those are
demo/eval orchestration, off-limits to the investigator itself.
"""

import os

import httpx
from langchain_core.tools import tool

INCIDENT_CONTROLLER_URL = os.environ.get("INCIDENT_CONTROLLER_URL", "http://localhost:58006")


@tool
def get_recent_changes(service: str = "") -> str:
    """Look up recently recorded deployments/configuration changes.

    Pass a service name (e.g. "payment-service") to filter, or leave empty to
    see changes across all services. Returns each change's field, old/new
    value, version, and timestamp.
    """
    params = {"service": service} if service else {}
    try:
        resp = httpx.get(f"{INCIDENT_CONTROLLER_URL}/control/changes", params=params, timeout=10.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        return f"error querying change log: {exc}"

    changes = resp.json().get("changes", [])
    if not changes:
        return f"no recent changes found (service={service!r})"

    lines = [
        f"{c['timestamp']} {c['service']}: {c['field']} changed from {c['from']} to {c['to']} "
        f"(version={c.get('version')})"
        for c in changes
    ]
    return "\n".join(lines)

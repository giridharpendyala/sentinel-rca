"""The ONLY mutating capability anywhere under agents/.

apply_action is reachable exclusively from nodes/remediation.py, and only after
a human has approved the action via the interrupt() gate. Every other tool in
agents/tools/ is GET-only.
"""

import os

import httpx

INCIDENT_CONTROLLER_URL = os.environ.get("INCIDENT_CONTROLLER_URL", "http://localhost:58006")


def apply_action(action_type: str, target_service: str, params: dict) -> str:
    """POST an approved remediation action to incident-controller.

    NOTE: incident-controller does not yet expose a /control/actions/apply
    endpoint (only /control/incidents/*/start|stop and /control/changes exist
    today) -- this call will 404 until that endpoint is added. It's still wired
    up correctly end-to-end so it works the moment that endpoint exists, and
    fails loudly and safely (never silently) in the meantime.
    """
    try:
        resp = httpx.post(
            f"{INCIDENT_CONTROLLER_URL}/control/actions/apply",
            json={"action_type": action_type, "target_service": target_service, "params": params},
            timeout=10.0,
        )
        resp.raise_for_status()
        return f"action applied: {resp.json()}"
    except httpx.HTTPStatusError as exc:
        return (
            f"action NOT applied: incident-controller returned {exc.response.status_code} "
            f"for {action_type} on {target_service}. This endpoint does not exist yet on "
            f"incident-controller -- the approval flow worked, but there is nothing on the "
            f"other end to actually perform the action."
        )
    except httpx.HTTPError as exc:
        return f"action NOT applied: error calling incident-controller: {exc}"

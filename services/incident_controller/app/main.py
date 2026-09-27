from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from telemetry import setup_metrics, setup_tracing, setup_logging

SERVICE_NAME = "incident-controller"
INCIDENTS_DIR = Path("/app/incidents")

SERVICE_PORTS = {
    "checkout-service": 8001,
    "cart-service": 8002,
    "pricing-service": 8003,
    "payment-service": 8004,
}

class ActionApplyRequest(BaseModel):
    action_type: str
    target_service: str
    params: dict = {}


app = FastAPI(title=SERVICE_NAME)
setup_metrics(app, SERVICE_NAME)
setup_tracing(app, SERVICE_NAME)
logger = setup_logging(SERVICE_NAME)

change_log: list[dict] = []
armed: dict | None = None  # {"incident_id": str, "service": str}


def _load_incident(incident_id: str) -> dict:
    path = INCIDENTS_DIR / f"{incident_id}.yaml"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"incident fixture not found: eval/incidents/{incident_id}.yaml",
        )
    with open(path) as f:
        data = yaml.safe_load(f)
    if not data or "fault" not in data:
        raise HTTPException(status_code=422, detail=f"incident fixture {incident_id}.yaml is missing a 'fault' block")
    return data


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/control/incidents/{incident_id}/start")
async def start_incident(incident_id: str):
    global armed

    incident = _load_incident(incident_id)
    fault = incident["fault"]
    service = fault["service"]

    if service not in SERVICE_PORTS:
        raise HTTPException(status_code=422, detail=f"unknown target service: {service}")

    cl = fault.get("change_log")
    if cl:
        change_log.append(
            {
                "incident_id": incident_id,
                "service": service,
                "field": cl.get("field"),
                "from": cl.get("from"),
                "to": cl.get("to"),
                "version": cl.get("version"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    port = SERVICE_PORTS[service]
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"http://{service}:{port}/admin/fault",
            json={"type": fault["type"], "params": fault.get("params", {})},
        )
        resp.raise_for_status()

    armed = {"incident_id": incident_id, "service": service}
    logger.info("incident armed", extra={"incident_id": incident_id, "service": service, "fault_type": fault["type"]})
    return {"incident_id": incident_id, "armed": True, "alert_text": incident.get("alert_text")}


@app.post("/control/incidents/{incident_id}/stop")
async def stop_incident(incident_id: str):
    global armed

    if not armed or armed["incident_id"] != incident_id:
        raise HTTPException(status_code=409, detail=f"incident {incident_id} is not currently armed")

    service = armed["service"]
    port = SERVICE_PORTS[service]
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.delete(f"http://{service}:{port}/admin/fault")
        resp.raise_for_status()

    armed = None
    logger.info("incident stopped", extra={"incident_id": incident_id, "service": service})
    return {"incident_id": incident_id, "armed": False}


@app.get("/control/changes")
def get_changes(service: str | None = None, since: str | None = None):
    results = change_log
    if service:
        results = [c for c in results if c["service"] == service]
    if since:
        results = [c for c in results if c["timestamp"] >= since]
    return {"changes": results}


@app.get("/control/status")
def get_status():
    return {"armed": armed}


@app.post("/control/actions/apply")
async def apply_remediation(req: ActionApplyRequest):
    global armed
    change_log.append(
        {
            "incident_id": armed.get("incident_id") if armed else "manual-remediation",
            "service": req.target_service,
            "field": "REMEDIATION",
            "from": "faulted",
            "to": "restored",
            "version": "remediation-applied",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": req.params.get("recommended_action", req.action_type),
        }
    )

    disarm_detail = "no fault active or service not found"
    if req.target_service in SERVICE_PORTS:
        port = SERVICE_PORTS[req.target_service]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.delete(f"http://{req.target_service}:{port}/admin/fault")
                disarm_detail = f"status: {resp.status_code}"
        except Exception as exc:
            disarm_detail = f"service call failed: {exc}"

    if armed and armed.get("service") == req.target_service:
        armed = None

    logger.info(
        "remediation action applied",
        extra={"target_service": req.target_service, "action_type": req.action_type, "params": req.params},
    )
    return {
        "status": "applied",
        "target_service": req.target_service,
        "action_type": req.action_type,
        "disarm_detail": disarm_detail,
        "message": f"Remediation action applied successfully to {req.target_service}.",
    }



@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled exception", extra={"path": request.url.path, "error": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "internal server error"})

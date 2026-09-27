"""FastAPI server for the interactive Web Test Page and Agents API (port 58010).

Provides:
- Static file serving for the rich Web Test UI
- Live status checks for all stack components
- Incidents catalogue from eval/incidents/*.yaml
- Control plane integration (start/stop faults and load)
- Real-time Server-Sent Events (SSE) streaming for multi-agent investigations
- Human-in-the-loop remediation approval endpoints
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import httpx
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.graph import build_graph
from agents.tracing import flush_langfuse_handler, get_handler_trace_url, get_langfuse_handler, trace_url
from langgraph.types import Command

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

UI_DIR = Path(__file__).resolve().parent / "ui"
INCIDENTS_DIR = _ROOT / "eval" / "incidents"

INCIDENT_CONTROLLER_URL = os.environ.get("INCIDENT_CONTROLLER_URL", "http://localhost:58006")
LOAD_GENERATOR_URL = "http://localhost:58005"

app = FastAPI(title="Capstone Agents API & Web Test Page", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active investigation sessions waiting for human approval: thread_id -> dict
ACTIVE_SESSIONS: dict[str, dict[str, Any]] = {}


class StartDemoRequest(BaseModel):
    incident_id: str
    load_rps: Optional[float] = None
    warmup_seconds: Optional[int] = None


class StopDemoRequest(BaseModel):
    incident_id: Optional[str] = None


class InvestigateRequest(BaseModel):
    incident_id: str
    alert_text: Optional[str] = None
    affected_service: Optional[str] = None
    auto_approve: bool = False
    agent_version: str = "v1-baseline"


class ResumeRequest(BaseModel):
    approved: bool


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "agents-api", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/incidents")
def list_incidents():
    """Return all 10 known incident scenario fixtures."""
    incidents = []
    if INCIDENTS_DIR.exists():
        for file in sorted(INCIDENTS_DIR.glob("INC-*.yaml")):
            try:
                data = yaml.safe_load(file.read_text(encoding="utf-8"))
                if data:
                    incidents.append(data)
            except Exception as exc:
                print(f"Error reading {file}: {exc}")
    return {"incidents": incidents}


@app.get("/api/status")
async def get_stack_status():
    """Check connectivity to all observability infra and synthetic microservices."""
    checks = [
        {"name": "Prometheus", "url": "http://localhost:59090/-/healthy", "port": 59090},
        {"name": "Loki", "url": "http://localhost:53100/ready", "port": 53100},
        {"name": "Tempo", "url": "http://localhost:53201/ready", "port": 53201},
        {"name": "Grafana", "url": "http://localhost:53300/api/health", "port": 53300},
        {"name": "Langfuse web", "url": "http://localhost:54000/api/public/health", "port": 54000},
        {"name": "incident-controller", "url": f"{INCIDENT_CONTROLLER_URL}/healthz", "port": 58006},
        {"name": "checkout-service", "url": "http://localhost:58001/healthz", "port": 58001},
        {"name": "cart-service", "url": "http://localhost:58002/healthz", "port": 58002},
        {"name": "pricing-service", "url": "http://localhost:58003/healthz", "port": 58003},
        {"name": "payment-service", "url": "http://localhost:58004/healthz", "port": 58004},
        {"name": "load-generator", "url": f"{LOAD_GENERATOR_URL}/healthz", "port": 58005},
    ]

    results = []
    async with httpx.AsyncClient(timeout=2.0) as client:
        for c in checks:
            try:
                resp = await client.get(c["url"])
                reachable = resp.status_code in (200, 204)
                status_str = "OK" if reachable else f"HTTP {resp.status_code}"
            except Exception:
                reachable = False
                status_str = "UNREACHABLE"
            results.append({
                "name": c["name"],
                "port": c["port"],
                "reachable": reachable,
                "status": status_str,
            })
    return {"services": results, "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/api/demo/start")
async def start_demo(req: StartDemoRequest):
    """Arm the incident fault and start load generator."""
    fixture_path = INCIDENTS_DIR / f"{req.incident_id}.yaml"
    if not fixture_path.exists():
        raise HTTPException(status_code=404, detail=f"Incident fixture {req.incident_id} not found.")

    fixture = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    rps = req.load_rps or fixture.get("load_rps", 15)
    fault = fixture.get("fault", {})
    fault_type = fault.get("type", "none")

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Start load
        load_resp = await client.post(f"{LOAD_GENERATOR_URL}/admin/start", json={"rps": rps})
        load_ok = load_resp.status_code == 200

        # 2. Arm fault if not 'none'
        armed_ok = True
        arm_detail = "no fault armed"
        if fault_type != "none":
            arm_resp = await client.post(f"{INCIDENT_CONTROLLER_URL}/control/incidents/{req.incident_id}/start")
            armed_ok = arm_resp.status_code == 200
            arm_detail = arm_resp.json() if armed_ok else f"status {arm_resp.status_code}"

    return {
        "incident_id": req.incident_id,
        "load_started": load_ok,
        "load_rps": rps,
        "fault_armed": armed_ok,
        "arm_detail": arm_detail,
        "alert_text": fixture.get("alert_text", ""),
        "target_service": fixture.get("target_service", "checkout-service"),
    }


@app.post("/api/demo/stop")
async def stop_demo(req: StopDemoRequest):
    """Disarm any active fault and stop load generator."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Stop load
        try:
            await client.post(f"{LOAD_GENERATOR_URL}/admin/stop")
        except Exception:
            pass

        # Disarm fault
        if req.incident_id:
            try:
                await client.post(f"{INCIDENT_CONTROLLER_URL}/control/incidents/{req.incident_id}/stop")
            except Exception:
                pass
    return {"status": "stopped"}


@app.post("/api/investigate")
async def start_investigation(req: InvestigateRequest):
    """Run the multi-agent investigation and stream steps as Server-Sent Events (SSE)."""
    thread_id = f"inv-{req.incident_id}-{uuid.uuid4().hex[:8]}"

    # Resolve alert & service
    alert_text = req.alert_text or ""
    affected_service = req.affected_service or "checkout-service"

    fixture_path = INCIDENTS_DIR / f"{req.incident_id}.yaml"
    if fixture_path.exists():
        data = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
        if not alert_text:
            alert_text = data.get("alert_text", "").strip()
        if not req.affected_service:
            affected_service = data.get("target_service", "checkout-service")

    async def event_generator() -> AsyncGenerator[str, None]:
        start_time = time.perf_counter()
        yield f"event: init\ndata: {json.dumps({'thread_id': thread_id, 'incident_id': req.incident_id, 'affected_service': affected_service, 'alert_text': alert_text})}\n\n"

        initial_state = {
            "incident_id": req.incident_id,
            "alert_text": alert_text,
            "affected_service": affected_service,
            "time_window": {"minutes_back": 15, "start_iso": datetime.now(timezone.utc).isoformat()},
            "messages": [],
            "evidence": [],
            "tool_call_log": [],
            "hypotheses": [],
            "rca": None,
            "pending_action": None,
            "iterations": 0,
            "errors": [],
        }

        graph = build_graph()
        langfuse_handler = get_langfuse_handler(tags=[req.incident_id, req.agent_version], session_id=thread_id)
        callbacks = [langfuse_handler] if langfuse_handler else []
        config = {
            "configurable": {"thread_id": thread_id},
            "callbacks": callbacks,
            "metadata": {
                "langfuse_session_id": thread_id,
                "langfuse_tags": [req.incident_id, req.agent_version] if req.agent_version else [req.incident_id],
                "langfuse_user_id": "operator",
            },
        }

        step_input: Any = initial_state
        final_state: dict[str, Any] = {}

        try:
            while True:
                interrupted = False
                interrupt_payload = None

                # LangGraph synchronous stream run in executor to keep FastAPI async
                def run_stream():
                    updates = []
                    for output in graph.stream(step_input, config=config, stream_mode="updates"):
                        updates.append(output)
                    return updates

                loop = asyncio.get_running_loop()
                updates = await loop.run_in_executor(None, run_stream)

                for output in updates:
                    if isinstance(output, tuple):
                        output = output[1] if len(output) > 1 and isinstance(output[1], dict) else {}
                    if not isinstance(output, dict):
                        continue

                    for node_name, node_update in output.items():
                        if node_name == "__interrupt__" or not isinstance(node_update, dict):
                            continue

                        payload = {
                            "node": node_name,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "iterations": node_update.get("iterations"),
                            "hypotheses": node_update.get("hypotheses", []),
                            "pending_action": node_update.get("pending_action"),
                            "evidence": node_update.get("evidence", []),
                            "errors": node_update.get("errors", []),
                        }
                        if "rca" in node_update and node_update["rca"]:
                            rca_val = node_update["rca"]
                            payload["rca"] = rca_val if isinstance(rca_val, dict) else rca_val.model_dump()

                        yield f"event: step\ndata: {json.dumps(payload)}\n\n"
                        await asyncio.sleep(0.1)

                state_snapshot = graph.get_state(config)
                if state_snapshot.values:
                    final_state = dict(state_snapshot.values)

                # Check if paused at interrupt (remediation)
                if state_snapshot.next and "remediation" in state_snapshot.next:
                    for task in state_snapshot.tasks:
                        if task.interrupts:
                            interrupt_payload = task.interrupts[0].value
                            interrupted = True
                            break

                if not interrupted:
                    break

                # Save session for approval resumption
                ACTIVE_SESSIONS[thread_id] = {
                    "graph": graph,
                    "config": config,
                    "interrupt_payload": interrupt_payload,
                    "final_state": final_state,
                    "langfuse_handler": langfuse_handler,
                }

                yield f"event: interrupt\ndata: {json.dumps({'thread_id': thread_id, 'payload': interrupt_payload})}\n\n"

                # Wait for approval signal from POST /api/investigate/{thread_id}/resume
                # or auto-approve if requested
                if req.auto_approve:
                    approved = True
                else:
                    # Wait up to 120 seconds for operator response
                    approved = False
                    wait_start = time.time()
                    while time.time() - wait_start < 120:
                        sess = ACTIVE_SESSIONS.get(thread_id, {})
                        if "user_approval" in sess:
                            approved = sess["user_approval"]
                            del ACTIVE_SESSIONS[thread_id]
                            break
                        await asyncio.sleep(1.0)

                step_input = Command(resume={"approved": approved})
                yield f"event: resume\ndata: {json.dumps({'approved': approved})}\n\n"

            # Investigation completed
            flush_langfuse_handler(langfuse_handler)
            elapsed_sec = round(time.perf_counter() - start_time, 2)
            trace_id_url = get_handler_trace_url(langfuse_handler)

            rca_dict = None
            if final_state.get("rca"):
                r = final_state["rca"]
                rca_dict = r if isinstance(r, dict) else r.model_dump()

            yield f"event: complete\ndata: {json.dumps({'thread_id': thread_id, 'elapsed_seconds': elapsed_sec, 'trace_url': trace_id_url, 'rca': rca_dict, 'evidence_count': len(final_state.get('evidence', [])), 'tool_calls': len(final_state.get('tool_call_log', []))})}\n\n"

        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/investigate/{thread_id}/resume")
def resume_investigation(thread_id: str, req: ResumeRequest):
    """Submit human approval to resume an interrupted investigation."""
    if thread_id not in ACTIVE_SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found or already completed.")
    ACTIVE_SESSIONS[thread_id]["user_approval"] = req.approved
    return {"status": "resumed", "approved": req.approved}


# Mount UI static files
if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
@app.get("/ui", response_class=HTMLResponse)
def get_ui():
    """Serve the Web Test Page HTML."""
    index_file = UI_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>UI files are being initialized... please refresh shortly.</h1>")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agents.api:app", host="0.0.0.0", port=58010, reload=False)

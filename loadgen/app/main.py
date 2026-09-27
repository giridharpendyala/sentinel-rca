import asyncio
import os
import random

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from telemetry import setup_metrics, setup_tracing, setup_logging

SERVICE_NAME = "load-generator"
CHECKOUT_SERVICE_URL = os.environ.get("CHECKOUT_SERVICE_URL", "http://checkout-service:8001")

app = FastAPI(title=SERVICE_NAME)
setup_metrics(app, SERVICE_NAME)
setup_tracing(app, SERVICE_NAME)
logger = setup_logging(SERVICE_NAME)

state = {
    "running": False,
    "rps": 0.0,
    "total_requests": 0,
    "total_errors": 0,
}
_task: asyncio.Task | None = None


class StartRequest(BaseModel):
    rps: float = 2.0


MAX_CONCURRENCY = 200


async def _send_one(client: httpx.AsyncClient, sem: asyncio.Semaphore) -> None:
    async with sem:
        try:
            resp = await client.post(f"{CHECKOUT_SERVICE_URL}/checkout")
            state["total_requests"] += 1
            if resp.status_code >= 400:
                state["total_errors"] += 1
        except httpx.HTTPError as exc:
            state["total_requests"] += 1
            state["total_errors"] += 1
            logger.warning("checkout request failed", extra={"error": str(exc)})


async def _drive_traffic() -> None:
    # Fire requests on a fixed schedule (arrival rate = rps) instead of waiting for
    # each response, so a slow/saturated downstream shows up as queueing/errors on
    # the target service rather than silently throttling our own send rate.
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    async with httpx.AsyncClient(timeout=10.0) as client:
        while state["running"]:
            base_delay = 1.0 / state["rps"] if state["rps"] > 0 else 1.0
            asyncio.create_task(_send_one(client, sem))
            await asyncio.sleep(random.uniform(base_delay * 0.7, base_delay * 1.3))


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/admin/start")
async def start(req: StartRequest):
    global _task
    state["rps"] = req.rps
    if not state["running"]:
        state["running"] = True
        _task = asyncio.create_task(_drive_traffic())
        logger.info("load generation started", extra={"rps": req.rps})
    else:
        logger.info("load generation rps updated", extra={"rps": req.rps})
    return {"running": True, "rps": state["rps"]}


@app.post("/admin/stop")
def stop():
    state["running"] = False
    logger.info("load generation stopped")
    return {"running": False}


@app.get("/admin/status")
def status():
    return state

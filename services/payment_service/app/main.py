import asyncio
import os
import random
import threading
import time

import psutil
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter
from pydantic import BaseModel

from telemetry import setup_metrics, setup_tracing, setup_logging, FaultState
from telemetry.metrics import make_gauge

from .db_pool import SimulatedDBPool

SERVICE_NAME = "payment-service"
DEFAULT_POOL_SIZE = 100
DEFAULT_ACQUIRE_TIMEOUT_S = 2.0
RESTART_COUNTER_FILE = "/tmp/restart_count"

app = FastAPI(title=SERVICE_NAME)
setup_metrics(app, SERVICE_NAME)
setup_tracing(app, SERVICE_NAME)
logger = setup_logging(SERVICE_NAME)

fault_state = FaultState()
pool = SimulatedDBPool(logger, size=DEFAULT_POOL_SIZE, acquire_timeout_s=DEFAULT_ACQUIRE_TIMEOUT_S)
lock_contention: dict | None = None

pool_active_gauge = make_gauge("payment_db_pool_active", "Active connections currently checked out")
pool_size_gauge = make_gauge("payment_db_pool_size", "Configured size of the simulated DB pool")
pool_size_gauge.set(DEFAULT_POOL_SIZE)

service_restarts_total = Counter(
    "service_restarts_total", "Cumulative number of times this service process has (re)started"
)

_oom_stop = threading.Event()
_oom_thread: threading.Thread | None = None


def _bump_restart_counter() -> int:
    count = 0
    try:
        with open(RESTART_COUNTER_FILE) as f:
            count = int((f.read() or "0").strip())
    except (FileNotFoundError, ValueError):
        count = 0
    count += 1
    with open(RESTART_COUNTER_FILE, "w") as f:
        f.write(str(count))
    return count


# Increment-and-persist before anything else, so a simulated OOM kill (os._exit)
# followed by a container restart is reflected cumulatively in the metric.
_restart_count = _bump_restart_counter()
service_restarts_total.inc(_restart_count)


def _start_oom_monitor(threshold_mb: float) -> None:
    global _oom_thread
    _stop_oom_monitor()
    _oom_stop.clear()
    proc = psutil.Process()

    def monitor() -> None:
        while not _oom_stop.is_set():
            rss_mb = proc.memory_info().rss / (1024 * 1024)
            if rss_mb >= threshold_mb:
                logger.error(
                    "memory threshold exceeded, simulating OOM kill",
                    extra={"rss_mb": rss_mb, "threshold_mb": threshold_mb},
                )
                os._exit(137)
            time.sleep(1.0)

    _oom_thread = threading.Thread(target=monitor, daemon=True)
    _oom_thread.start()


def _stop_oom_monitor() -> None:
    _oom_stop.set()


class FaultRequest(BaseModel):
    type: str
    params: dict = {}


class ChargeRequest(BaseModel):
    amount: float = 42.00
    customer_email: str = "jane.doe@example.com"
    card_number: str = "4111-1111-1111-1111"


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/admin/fault")
def arm_fault(req: FaultRequest):
    global pool, lock_contention

    if req.type == "db_pool_exhaustion":
        new_size = int(req.params.get("pool_size", 50))
        pool = SimulatedDBPool(logger, size=new_size, acquire_timeout_s=pool.acquire_timeout_s)
        pool_size_gauge.set(new_size)
    elif req.type == "lock_contention":
        lock_contention = {
            "probability": float(req.params.get("probability", 0.3)),
            "delay_seconds": float(req.params.get("delay_seconds", 3.0)),
        }
    elif req.type == "restart_on_oom":
        mb_per_tick = float(req.params.get("memory_leak_mb_per_tick", 20))
        threshold_mb = float(req.params.get("threshold_mb", 300))
        fault_state.arm("memory_leak", {"mb_per_tick": mb_per_tick})
        _start_oom_monitor(threshold_mb)
    else:
        fault_state.arm(req.type, req.params)

    logger.info("fault armed", extra={"fault_type": req.type, "params": req.params})
    return {"armed": req.type}


@app.delete("/admin/fault")
def disarm_fault():
    global pool, lock_contention

    pool = SimulatedDBPool(logger, size=DEFAULT_POOL_SIZE, acquire_timeout_s=DEFAULT_ACQUIRE_TIMEOUT_S)
    pool_size_gauge.set(DEFAULT_POOL_SIZE)
    lock_contention = None
    _stop_oom_monitor()
    fault_state.disarm()

    logger.info("fault disarmed")
    return {"armed": None}


@app.post("/charge")
async def charge(req: ChargeRequest):
    fault_state.apply_latency()

    try:
        fault_state.maybe_raise(RuntimeError, "payment processing failed")
    except RuntimeError as exc:
        logger.error("payment processing error", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if lock_contention and random.random() < lock_contention["probability"]:
        logger.error("Lock wait timeout exceeded")
        await asyncio.sleep(lock_contention["delay_seconds"])

    async with pool.acquire():
        pool_active_gauge.set(pool.active)
        logger.info(
            "charge processed",
            extra={
                "amount": req.amount,
                "customer_email": req.customer_email,
                "card_number": req.card_number,
            },
        )
    pool_active_gauge.set(pool.active)

    return {"status": "charged", "amount": req.amount}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled exception", extra={"path": request.url.path, "error": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "internal server error"})

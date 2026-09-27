import random

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from telemetry import setup_metrics, setup_tracing, setup_logging, FaultState

SERVICE_NAME = "cart-service"

app = FastAPI(title=SERVICE_NAME)
setup_metrics(app, SERVICE_NAME)
setup_tracing(app, SERVICE_NAME)
logger = setup_logging(SERVICE_NAME)

fault_state = FaultState()


class FaultRequest(BaseModel):
    type: str
    params: dict = {}


class ComputeRequest(BaseModel):
    items: list[str] = ["item-1", "item-2"]


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/admin/fault")
def arm_fault(req: FaultRequest):
    fault_state.arm(req.type, req.params)
    logger.info("fault armed", extra={"fault_type": req.type, "params": req.params})
    return {"armed": req.type}


@app.delete("/admin/fault")
def disarm_fault():
    fault_state.disarm()
    logger.info("fault disarmed")
    return {"armed": None}


def _maybe_inject_application_exception() -> None:
    """INC-10: a real, probabilistic unhandled-exception bug, not just a raised error."""
    active = fault_state.get()
    if active and active["type"] == "exception":
        probability = float(active["params"].get("probability", 0.5))
        if random.random() < probability:
            cart_index: dict[str, float] = {"item-1": 9.99}
            # Deliberately triggers a real KeyError when the requested item isn't priced.
            _ = cart_index["item-does-not-exist"]


@app.post("/compute")
def compute(req: ComputeRequest):
    fault_state.apply_latency()

    try:
        _maybe_inject_application_exception()
        fault_state.maybe_raise(RuntimeError, "cart computation failed")
    except KeyError as exc:
        logger.error("unhandled KeyError in cart computation", extra={"key": str(exc)})
        raise HTTPException(status_code=500, detail="internal cart error") from exc
    except RuntimeError as exc:
        logger.error("cart computation error", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    total = round(sum(random.uniform(5, 50) for _ in req.items), 2)
    logger.info("cart computed", extra={"items": req.items, "total": total})
    return {"items": req.items, "total": total}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled exception", extra={"path": request.url.path, "error": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "internal server error"})

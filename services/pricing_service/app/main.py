import random

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from telemetry import setup_metrics, setup_tracing, setup_logging, FaultState

SERVICE_NAME = "pricing-service"

VALID_STRATEGIES = {"standard", "promo", "clearance"}

app = FastAPI(title=SERVICE_NAME)
setup_metrics(app, SERVICE_NAME)
setup_tracing(app, SERVICE_NAME)
logger = setup_logging(SERVICE_NAME)

fault_state = FaultState()
current_strategy = "standard"


class FaultRequest(BaseModel):
    type: str
    params: dict = {}


class PriceRequest(BaseModel):
    items: list[str] = ["item-1", "item-2"]


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/admin/fault")
def arm_fault(req: FaultRequest):
    global current_strategy
    fault_state.arm(req.type, req.params)
    if req.type == "config_error":
        current_strategy = req.params.get("invalid_strategy", "unknown-strategy")
    logger.info("fault armed", extra={"fault_type": req.type, "params": req.params})
    return {"armed": req.type}


@app.delete("/admin/fault")
def disarm_fault():
    global current_strategy
    fault_state.disarm()
    current_strategy = "standard"
    logger.info("fault disarmed")
    return {"armed": None}


@app.post("/compute")
def compute(req: PriceRequest):
    fault_state.apply_latency()  # INC-05: downstream API slowdown

    if current_strategy not in VALID_STRATEGIES:
        logger.error(
            "invalid pricing strategy configured",
            extra={"pricing_strategy": current_strategy},
        )
        raise HTTPException(status_code=422, detail=f"invalid PRICING_STRATEGY: {current_strategy}")

    try:
        fault_state.maybe_raise(RuntimeError, "pricing computation failed")
    except RuntimeError as exc:
        logger.error("pricing computation error", extra={"error": str(exc)})
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    quote = round(sum(random.uniform(10, 100) for _ in req.items), 2)
    logger.info("price computed", extra={"items": req.items, "quote": quote, "strategy": current_strategy})
    return {"items": req.items, "quote": quote, "strategy": current_strategy}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled exception", extra={"path": request.url.path, "error": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "internal server error"})

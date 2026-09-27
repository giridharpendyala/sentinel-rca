import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from telemetry import setup_metrics, setup_tracing, setup_logging

SERVICE_NAME = "checkout-service"

CART_SERVICE_URL = os.environ.get("CART_SERVICE_URL", "http://cart-service:8002")
PRICING_SERVICE_URL = os.environ.get("PRICING_SERVICE_URL", "http://pricing-service:8003")
PAYMENT_SERVICE_URL = os.environ.get("PAYMENT_SERVICE_URL", "http://payment-service:8004")

app = FastAPI(title=SERVICE_NAME)
setup_metrics(app, SERVICE_NAME)
setup_tracing(app, SERVICE_NAME)
logger = setup_logging(SERVICE_NAME)


class CheckoutRequest(BaseModel):
    items: list[str] = ["item-1", "item-2"]
    customer_email: str = "jane.doe@example.com"
    card_number: str = "4111-1111-1111-1111"


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/checkout")
async def checkout(req: CheckoutRequest = CheckoutRequest()):
    async with httpx.AsyncClient(timeout=10.0) as client:
        cart_resp = await client.post(f"{CART_SERVICE_URL}/compute", json={"items": req.items})
        if cart_resp.status_code >= 400:
            logger.error("cart service failed", extra={"status_code": cart_resp.status_code})
            return JSONResponse(status_code=502, content={"detail": "cart service failed", "upstream": cart_resp.text})

        pricing_resp = await client.post(f"{PRICING_SERVICE_URL}/compute", json={"items": req.items})
        if pricing_resp.status_code >= 400:
            logger.error("pricing service failed", extra={"status_code": pricing_resp.status_code})
            return JSONResponse(
                status_code=502, content={"detail": "pricing service failed", "upstream": pricing_resp.text}
            )

        payment_resp = await client.post(
            f"{PAYMENT_SERVICE_URL}/charge",
            json={
                "amount": pricing_resp.json()["quote"],
                "customer_email": req.customer_email,
                "card_number": req.card_number,
            },
        )
        if payment_resp.status_code >= 400:
            logger.error("payment service failed", extra={"status_code": payment_resp.status_code})
            return JSONResponse(
                status_code=502 if payment_resp.status_code != 503 else 503,
                content={"detail": "payment service failed", "upstream": payment_resp.text},
            )

    logger.info("checkout completed", extra={"items": req.items})
    return {
        "cart": cart_resp.json(),
        "pricing": pricing_resp.json(),
        "payment": payment_resp.json(),
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled exception", extra={"path": request.url.path, "error": str(exc)})
    return JSONResponse(status_code=500, content={"detail": "internal server error"})

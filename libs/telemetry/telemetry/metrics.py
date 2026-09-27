from prometheus_client import Counter, Histogram, Gauge, make_asgi_app
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import time

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["service", "path", "method"],
)
REQUEST_COUNT = Counter(
    "http_requests_total",
    "HTTP request count",
    ["service", "path", "method", "status"],
)


class _MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, service_name: str):
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        status = "500"
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            elapsed = time.perf_counter() - start
            path = request.url.path
            REQUEST_LATENCY.labels(self.service_name, path, request.method).observe(elapsed)
            REQUEST_COUNT.labels(self.service_name, path, request.method, status).inc()


def setup_metrics(app, service_name: str) -> None:
    """Attach Prometheus instrumentation + mount /metrics on a FastAPI app."""
    app.add_middleware(_MetricsMiddleware, service_name=service_name)
    app.mount("/metrics", make_asgi_app())


def make_gauge(name: str, description: str, labelnames: list[str] | None = None) -> Gauge:
    return Gauge(name, description, labelnames or [])

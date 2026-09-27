import logging
import os
import sys

from pythonjsonlogger import jsonlogger

try:
    from logging_loki import LokiHandler
except ImportError:  # pragma: no cover - optional dependency guard
    LokiHandler = None


def setup_logging(service_name: str) -> logging.Logger:
    """Configure structured JSON logging to stdout plus a direct push to Loki."""
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(
        jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(stdout_handler)

    loki_url = os.environ.get("LOKI_URL")
    if loki_url and LokiHandler is not None:
        loki_handler = LokiHandler(
            url=f"{loki_url}/loki/api/v1/push",
            tags={"service": service_name},
            version="1",
        )
        logger.addHandler(loki_handler)

    logger.propagate = False
    return logger

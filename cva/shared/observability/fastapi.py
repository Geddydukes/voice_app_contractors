"""FastAPI instrumentation helpers."""

from __future__ import annotations

import logging
import time
from typing import Callable

from fastapi import FastAPI, Request
from starlette.responses import Response

from .sanitize import sanitize_value
from .tracing import configure_logging, generate_trace_id, reset_trace_id, set_trace_id


def instrument_app(app: FastAPI, service_name: str) -> logging.Logger:
    """Attach tracing and latency logging middleware to ``app``."""

    configure_logging(service_name)
    logger = logging.getLogger(service_name)

    @app.middleware("http")
    async def _trace_middleware(request: Request, call_next: Callable[[Request], Response]):
        incoming_trace = request.headers.get("X-Trace-ID")
        trace_id = incoming_trace or generate_trace_id()
        token = set_trace_id(trace_id)
        response: Response | None = None
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "HTTP %s %s failed after %.2fms",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
        else:
            duration_ms = (time.perf_counter() - start) * 1000
            client_ip = request.client.host if request.client else "unknown"
            logger.info(
                "HTTP %s %s -> %s in %.2fms client=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                sanitize_value(client_ip),
            )
        finally:
            if response is not None:
                response.headers["X-Trace-ID"] = trace_id
            reset_trace_id(token)
        return response  # type: ignore[return-value]

    logger.info("Observability middleware attached.")
    return logger

"""Shared observability helpers for trace propagation and logging."""

from __future__ import annotations

from .sanitize import sanitize_value
from .tracing import (
    TraceIdFilter,
    configure_logging,
    generate_trace_id,
    get_trace_id,
    reset_trace_id,
    set_trace_id,
)

try:  # pragma: no cover - optional dependency for CLI usage
    from .fastapi import instrument_app
except ModuleNotFoundError:  # pragma: no cover - FastAPI optional for admin tooling
    def instrument_app(*_args, **_kwargs):  # type: ignore[override]
        raise ModuleNotFoundError(
            "FastAPI is required for instrument_app but is not installed in this environment."
        )

__all__ = [
    "TraceIdFilter",
    "configure_logging",
    "generate_trace_id",
    "get_trace_id",
    "instrument_app",
    "reset_trace_id",
    "sanitize_value",
    "set_trace_id",
]

"""Tracing utilities shared across services."""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from typing import Iterator
from uuid import uuid4

_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)


def generate_trace_id() -> str:
    """Return a random hexadecimal trace identifier."""

    return uuid4().hex


def get_trace_id(default: str | None = None) -> str | None:
    """Fetch the current trace identifier if set."""

    trace_id = _trace_id.get()
    if trace_id is None:
        return default
    return trace_id


def set_trace_id(trace_id: str | None) -> contextvars.Token[str | None]:
    """Bind a trace identifier to the current execution context."""

    if trace_id is None:
        trace_id = generate_trace_id()
    return _trace_id.set(trace_id)


def reset_trace_id(token: contextvars.Token[str | None]) -> None:
    """Reset the trace identifier using a previously returned token."""

    _trace_id.reset(token)


@contextmanager
def use_trace(trace_id: str | None = None) -> Iterator[str]:
    """Context manager that binds and resets the current trace id."""

    token = set_trace_id(trace_id)
    try:
        yield get_trace_id("-") or "-"
    finally:
        reset_trace_id(token)


class TraceIdFilter(logging.Filter):
    """Inject the active trace identifier into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - logging hook
        record.trace_id = get_trace_id("-") or "-"
        return True


_LOGGING_CONFIGURED = False


def configure_logging(service_name: str | None = None) -> None:
    """Configure root logging once with a consistent trace-aware formatter."""

    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    handler = logging.StreamHandler()
    handler.addFilter(TraceIdFilter())
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | trace=%(trace_id)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers = [handler]
    if service_name:
        logging.getLogger(service_name).setLevel(logging.INFO)

    _LOGGING_CONFIGURED = True

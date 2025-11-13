"""Utilities to sanitize sensitive values before logging."""

from __future__ import annotations

import re
from typing import Any

_EMAIL_PATTERN = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+)")
_PHONE_PATTERN = re.compile(r"(\+?\d{2})[\d\-\s]{3,}(\d{2})")


def _sanitize_string(value: str) -> str:
    """Redact phone numbers and email addresses from ``value``."""

    redacted = _EMAIL_PATTERN.sub(r"\1***\2", value)
    redacted = _PHONE_PATTERN.sub(r"\1***\2", redacted)
    return redacted


def sanitize_value(value: Any) -> Any:
    """Best-effort redaction of sensitive fields for logging contexts."""

    if value is None:
        return None
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, bytes):
        return "<bytes>"
    if isinstance(value, dict):
        return {k: sanitize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        sanitized = [sanitize_value(item) for item in value]
        return type(value)(sanitized) if not isinstance(value, set) else set(sanitized)
    return value

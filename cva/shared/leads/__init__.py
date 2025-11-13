"""Lead capture storage utilities shared across services."""

from .store import (
    LeadNotFoundError,
    LeadStore,
    MessageRecord,
    format_iso_timestamp,
)

__all__ = [
    "LeadStore",
    "LeadNotFoundError",
    "MessageRecord",
    "format_iso_timestamp",
]

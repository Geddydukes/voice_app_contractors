"""Pydantic models for telephony service APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class InboundCallRequest(BaseModel):
    """Payload delivered from a telephony provider on inbound call."""

    call_id: str = Field(..., description="Provider call identifier")
    from_number: str = Field(..., description="Caller phone number")
    to_number: str = Field(..., description="Destination number")
    started_at: datetime = Field(default_factory=datetime.utcnow)


class CallSessionResponse(BaseModel):
    """Information describing the streaming session for a call."""

    session_id: str
    stream_url: str
    expires_in_seconds: int = 300
    trace_id: str


class StreamChunk(BaseModel):
    """Wrapper for inbound audio chunk metadata."""

    sequence: int
    sample_rate: int
    audio_base64: str
    is_final: Optional[bool] = None

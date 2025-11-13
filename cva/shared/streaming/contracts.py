"""Typed streaming messages passed between telephony and conversation services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class StreamEventType(str, Enum):
    """Enumeration of streaming event categories."""

    AUDIO_IN = "audio_in"
    TRANSCRIPT = "transcript"
    LLM_RESPONSE = "llm_response"
    AUDIO_OUT = "audio_out"


@dataclass(slots=True)
class AudioChunk:
    """Inbound audio frame captured from the caller."""

    session_id: str
    sequence: int
    sample_rate: int
    payload: bytes
    trace_id: str | None = None


@dataclass(slots=True)
class TranscriptChunk:
    """Partial speech-to-text hypothesis."""

    session_id: str
    sequence: int
    text: str
    is_final: bool = False
    trace_id: str | None = None


@dataclass(slots=True)
class LLMResponseChunk:
    """Partial natural-language model response."""

    session_id: str
    sequence: int
    text: str
    is_final: bool = False
    trace_id: str | None = None


@dataclass(slots=True)
class TTSChunk:
    """Audio synthesized from the assistant response."""

    session_id: str
    sequence: int
    sample_rate: int
    payload: bytes
    is_final: bool = False
    trace_id: str | None = None


@dataclass(slots=True)
class StreamEvent:
    """Generic streaming event payload for websocket delivery."""

    event_type: StreamEventType
    sequence: int
    session_id: str
    payload: Dict[str, Any]
    trace_id: str | None = None

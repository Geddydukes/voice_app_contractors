"""Pydantic models used by the conversation orchestrator HTTP surface."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    """Represents a single conversational message stored in session memory."""

    role: Literal["user", "assistant", "tool"]
    content: str
    tool_name: Optional[str] = Field(default=None, description="Name of the tool that produced the message if applicable.")


class ConversationRequest(BaseModel):
    """Incoming request to the policy orchestrator."""

    session_id: str = Field(..., description="Unique identifier for the caller session.")
    text: str = Field(..., description="User provided utterance for this turn.")
    tone: str = Field(default="friendly", description="Desired response tone such as friendly or professional.")
    bilingual: bool = Field(default=True, description="If true responses are rendered in English and Spanish.")
    locale: str = Field(default="en", description="Locale driving policy heuristics, defaults to English.")
    trace_id: Optional[str] = Field(
        default=None,
        description="Optional trace identifier propagated across services.",
    )


class ToolPayload(BaseModel):
    """Structured result returned from the selected tool."""

    name: str
    success: bool
    data: dict


class ConversationResponse(BaseModel):
    """Structured output emitted by the orchestrator for each turn."""

    session_id: str
    reply: str
    decision: str
    tool: ToolPayload
    language: str = Field(default="en", description="Detected primary language for the session.")
    memory: List[ConversationTurn]
    trace_id: str = Field(default="-", description="Trace identifier attached to the request.")

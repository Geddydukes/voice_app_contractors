"""Conversation orchestrator service implementing policy engine and tools."""

from __future__ import annotations

from fastapi import FastAPI

from policy import PolicyEngine
from models import ConversationRequest, ConversationResponse
from shared.observability import instrument_app

app = FastAPI(title="Conversation Service")
logger = instrument_app(app, "conversation-service")
policy_engine = PolicyEngine()


@app.get("/health")
def health() -> dict[str, str]:
    """Service readiness probe."""

    return {"status": "ok", "service": "conversation"}


@app.post("/v1/policy/turn", response_model=ConversationResponse)
def policy_turn(request: ConversationRequest) -> ConversationResponse:
    """Process a single conversational turn through the orchestrator."""

    response = policy_engine.handle_turn(request)
    logger.info(
        "Policy turn session=%s decision=%s tool=%s",
        response.session_id,
        response.decision,
        response.tool.name,
    )
    return response

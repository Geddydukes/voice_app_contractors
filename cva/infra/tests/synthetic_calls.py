"""Synthetic QA harness validating multilingual scheduling flows."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
conversation_dir = ROOT / "conversation-service"
shared_dir = ROOT / "shared"
for path in (conversation_dir, shared_dir):
    if str(path) not in sys.path:
        sys.path.append(str(path))

from policy import PolicyEngine  # type: ignore  # noqa: E402
from models import ConversationRequest  # type: ignore  # noqa: E402
from shared.observability import configure_logging, generate_trace_id, reset_trace_id, set_trace_id  # noqa: E402

configure_logging("synthetic-tests")


def run_turn(engine: PolicyEngine, request: ConversationRequest) -> tuple[float, ConversationRequest]:
    trace_id = request.trace_id or generate_trace_id()
    token = set_trace_id(trace_id)
    start = time.perf_counter()
    try:
        response = engine.handle_turn(request)
    finally:
        reset_trace_id(token)
    latency = time.perf_counter() - start
    if latency >= 1.5:
        raise AssertionError(f"Latency {latency:.3f}s exceeded 1.5s budget for {request.text!r}")
    return latency, response


def main() -> None:
    engine = PolicyEngine()

    en_request = ConversationRequest(
        session_id="synthetic-en",
        text="I need to book a water heater install next week",
        tone="friendly",
        bilingual=False,
        locale="en",
        trace_id=generate_trace_id(),
    )
    en_latency, en_response = run_turn(engine, en_request)
    assert en_response.tool.name == "scheduler" and en_response.tool.success
    print(f"EN booking latency: {en_latency*1000:.2f}ms -> {en_response.reply}")

    es_request = ConversationRequest(
        session_id="synthetic-es",
        text="Hola, necesito instalar un calentador de agua la próxima semana",
        tone="cálido",
        bilingual=True,
        locale="es",
        trace_id=generate_trace_id(),
    )
    es_latency, es_response = run_turn(engine, es_request)
    assert es_response.language == "es"
    assert es_response.tool.name == "scheduler"
    print(f"ES booking latency: {es_latency*1000:.2f}ms -> {es_response.reply}")

    ooa_request = ConversationRequest(
        session_id="synthetic-ooa",
        text="Can you book a water heater install? I'm outside service area at 47.90,-122.50",
        tone="professional",
        bilingual=False,
        locale="en",
        trace_id=generate_trace_id(),
    )
    ooa_latency, ooa_response = run_turn(engine, ooa_request)
    assert ooa_response.tool.data.get("reason") == "out_of_area"
    print(f"Out-of-area latency: {ooa_latency*1000:.2f}ms -> {ooa_response.reply}")

    message_request = ConversationRequest(
        session_id="synthetic-message",
        text="Please book me for next week but if the calendar down just take a message only",
        tone="friendly",
        bilingual=True,
        locale="en",
        trace_id=generate_trace_id(),
    )
    message_latency, message_response = run_turn(engine, message_request)
    assert not message_response.tool.success
    assert "message" in message_response.reply.lower()
    print(f"Message-only latency: {message_latency*1000:.2f}ms -> {message_response.reply}")


if __name__ == "__main__":
    main()

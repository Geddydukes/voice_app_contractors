"""Local harness to exercise the conversation policy engine."""

from __future__ import annotations

import argparse
import json

from policy import PolicyEngine
from models import ConversationRequest
from shared.observability import configure_logging, generate_trace_id, reset_trace_id, set_trace_id


configure_logging("conversation-harness")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a sample turn through the conversation policy engine.")
    parser.add_argument("--session", default="demo-session", help="Session identifier for memory tracking.")
    parser.add_argument("--text", default="water heater install next week", help="Utterance to route through the orchestrator.")
    parser.add_argument("--tone", default="friendly", help="Desired tone for the response.")
    parser.add_argument("--locale", default="en", help="Locale hint for the language detector (en or es).")
    parser.add_argument("--bilingual", action="store_true", help="Render bilingual output (default true).")
    parser.add_argument("--monolingual", action="store_true", help="Force English-only response.")
    args = parser.parse_args()

    bilingual = True
    if args.monolingual:
        bilingual = False
    elif args.bilingual:
        bilingual = True

    engine = PolicyEngine()
    trace_id = generate_trace_id()
    request = ConversationRequest(
        session_id=args.session,
        text=args.text,
        tone=args.tone,
        bilingual=bilingual,
        locale=args.locale,
        trace_id=trace_id,
    )
    token = set_trace_id(trace_id)
    try:
        response = engine.handle_turn(request)
    finally:
        reset_trace_id(token)
    print(json.dumps(response.model_dump(), indent=2))


if __name__ == "__main__":
    main()

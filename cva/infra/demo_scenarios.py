"""Guided demo scenarios that exercise the end-to-end pilot flow."""

from __future__ import annotations

import argparse
import sys
import textwrap
from dataclasses import dataclass
from typing import Any, Iterable, TYPE_CHECKING

from . import INFRA_ROOT
from .cli import TENANTS_ROOT, load_profile_from_disk, seed_demo_data
from .tenant_profiles import BUILT_IN_PROFILES

parent_dir = INFRA_ROOT.parent
if str(parent_dir) not in sys.path:
    sys.path.append(str(parent_dir))

from shared.leads.store import LeadStore  # type: ignore  # noqa: E402

conversation_dir = INFRA_ROOT.parent / "conversation-service"
if str(conversation_dir) not in sys.path:
    sys.path.append(str(conversation_dir))

IMPORT_ERROR: ModuleNotFoundError | None = None
if TYPE_CHECKING:  # pragma: no cover - used for type hints only
    from policy import PolicyEngine  # type: ignore
    from models import ConversationResponse  # type: ignore

try:  # pragma: no cover - optional dependency for offline demos
    from policy import PolicyEngine  # type: ignore  # noqa: E402
    from models import ConversationRequest, ConversationResponse  # type: ignore  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover
    IMPORT_ERROR = exc
    PolicyEngine = Any  # type: ignore  # noqa: N806
    ConversationRequest = Any  # type: ignore  # noqa: N806
    ConversationResponse = Any  # type: ignore  # noqa: N806

from shared.observability import (  # noqa: E402
    configure_logging,
    generate_trace_id,
    reset_trace_id,
    set_trace_id,
)

configure_logging("demo")


@dataclass(frozen=True)
class Scenario:
    """Represents a scripted conversational journey."""

    slug: str
    description: str
    text: str
    tone: str
    bilingual: bool
    locale: str


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        slug="booking-en",
        description="English homeowner books a water heater installation with travel check.",
        text="Hi, I need a water heater install early next week.",
        tone="friendly",
        bilingual=False,
        locale="en",
    ),
    Scenario(
        slug="booking-es",
        description="Spanish-speaking caller receives a bilingual confirmation.",
        text="Hola, necesito programar una instalación de calentador de agua la próxima semana.",
        tone="cálido",
        bilingual=True,
        locale="es",
    ),
    Scenario(
        slug="message-only",
        description="Calendar outage fallback captures a message for staff follow-up.",
        text="If the calendar is down, can you just take my info for a water heater install?",
        tone="reassuring",
        bilingual=True,
        locale="en",
    ),
)


def run(engine: Any, scenario: Scenario) -> Any:
    request = ConversationRequest(
        session_id=f"demo-{scenario.slug}",
        text=scenario.text,
        tone=scenario.tone,
        bilingual=scenario.bilingual,
        locale=scenario.locale,
        trace_id=generate_trace_id(),
    )
    token = set_trace_id(request.trace_id)
    try:
        response = engine.handle_turn(request)
    finally:
        reset_trace_id(token)
    return response


def ensure_lead_store(tenant_id: str) -> LeadStore:
    tenant_dir = TENANTS_ROOT / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    lead_store_path = tenant_dir / "lead_store.sqlite3"
    return LeadStore(db_path=str(lead_store_path), tenant_id=tenant_id)


def render_summary(response: Any) -> str:
    reply = getattr(response, "reply", "(no reply)")
    language = getattr(response, "language", "en") or "en"
    segments = [f"Reply: {reply}", f"Language: {language}"]
    tool = getattr(response, "tool", None)
    if tool is not None:
        success = getattr(tool, "success", False)
        name = getattr(tool, "name", "tool")
        status = "success" if success else "fallback"
        segments.append(f"Tool: {name} ({status})")
    return "\n".join(segments)


def print_script(profile, tenant_id: str) -> None:
    print(
        textwrap.dedent(
            f"""
            === Live Demo Script for {profile.company_name} ({tenant_id}) ===
            1. Start the telephony harness: `python cva/telephony-service/harness.py --tenant {tenant_id}`
            2. In a new terminal run: `python -m cva admin:onboard {tenant_id} --owner-email demo@{tenant_id}.com --owner-password DemoPass123 --seed-demo`
            3. Use the scenarios below to narrate the assistant response while the audio stream plays.
            """
        ).strip()
    )
    for scenario in SCENARIOS:
        print(
            textwrap.dedent(
                f"""
                --- Scenario: {scenario.slug} ---
                {scenario.description}
                Prompt: {scenario.text}
                Tone: {scenario.tone} | Locale: {scenario.locale} | Bilingual: {scenario.bilingual}
                """
            ).rstrip()
        )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run scripted demo scenarios")
    parser.add_argument("tenant_id", help="Tenant to run demos against")
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="Seed the lead store with bilingual confirmation examples",
    )
    parser.add_argument(
        "--show-script",
        action="store_true",
        help="Print a narrated script without executing the policy engine",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    profile = load_profile_from_disk(TENANTS_ROOT / args.tenant_id) or BUILT_IN_PROFILES["plumber"]

    if args.show_script:
        print_script(profile, args.tenant_id)
        return 0

    if IMPORT_ERROR is not None:
        print(
            "Conversation service dependencies are missing. Install pydantic/fastapi to run live demos.",
            file=sys.stderr,
        )
        print_script(profile, args.tenant_id)
        return 1

    engine = PolicyEngine()
    lead_store = ensure_lead_store(args.tenant_id)
    if args.seed_demo:
        seed_demo_data(lead_store, profile)

    print(f"Running {len(SCENARIOS)} demo scenarios for {profile.company_name}\n")
    for scenario in SCENARIOS:
        response = run(engine, scenario)
        print(f"[{scenario.slug}] {render_summary(response)}\n")
    print("Demo complete. Leads recorded in the tenant database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

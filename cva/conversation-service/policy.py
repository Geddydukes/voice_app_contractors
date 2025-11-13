"""Dialog policy engine orchestrating tools and prompt templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from models import ConversationRequest, ConversationResponse, ConversationTurn, ToolPayload
from prompts import build_prompt, format_bilingual_message
from shared.observability import generate_trace_id, get_trace_id
from tools import NotifierTool, RetrievalAugmentedGenerator, SchedulerTool, ToolError, ToolResult

SPANISH_KEYWORDS = {
    "hola",
    "buenos",
    "gracias",
    "instalación",
    "agua",
    "caliente",
    "semana",
    "programar",
    "cita",
    "agendar",
    "mañana",
    "tarde",
    "por favor",
    "necesito",
    "calentador",
}


def _detect_language(text: str, *, default: str = "en") -> str:
    """Very lightweight language detection between English and Spanish."""

    lowered = text.lower()
    if any(keyword in lowered for keyword in SPANISH_KEYWORDS):
        return "es"
    if any(char in text for char in "áéíóúñü¡¿"):
        return "es"
    return default if default in {"en", "es"} else "en"


@dataclass
class SessionMemory:
    """Stores the conversation history for a given session."""

    session_id: str
    turns: List[ConversationTurn] = field(default_factory=list)
    language: str = "en"
    language_locked: bool = False
    greeting_sent: bool = False

    def add_turn(self, role: str, content: str, tool_name: str | None = None) -> None:
        self.turns.append(ConversationTurn(role=role, content=content, tool_name=tool_name))

    def recent_user_messages(self, limit: int = 5) -> List[str]:
        return [turn.content for turn in self.turns if turn.role == "user"][-limit:]

    def update_language(self, text: str, hint: str | None = None) -> str:
        if self.language_locked:
            return self.language
        hint_language = (hint or "").lower()
        if hint_language in {"en", "es"}:
            detected = hint_language
        else:
            detected = _detect_language(text, default=self.language)
        self.language = detected
        if detected != "en":
            self.language_locked = True
        return self.language


@dataclass
class PolicyDecision:
    """Represents the policy engine plan for the current turn."""

    decision: str
    tool: str


class PolicyEngine:
    """High level orchestrator for dialog policy and tool routing."""

    def __init__(
        self,
        rag_tool: RetrievalAugmentedGenerator | None = None,
        scheduler_tool: SchedulerTool | None = None,
        notifier_tool: NotifierTool | None = None,
    ) -> None:
        self._sessions: Dict[str, SessionMemory] = {}
        self.rag_tool = rag_tool or RetrievalAugmentedGenerator()
        self.scheduler_tool = scheduler_tool or SchedulerTool()
        self.notifier_tool = notifier_tool or NotifierTool()

    def handle_turn(self, request: ConversationRequest) -> ConversationResponse:
        session = self._sessions.setdefault(request.session_id, SessionMemory(session_id=request.session_id))
        session.add_turn(role="user", content=request.text)
        language = session.update_language(request.text, hint=request.locale)
        trace_id = request.trace_id or get_trace_id(None) or generate_trace_id()

        decision = self._decide(request)

        try:
            tool_result = self._execute(decision, request, session)
            reply_text = self._compose_reply(
                decision,
                tool_result,
                request,
                session,
                language=language,
                bilingual=request.bilingual,
            )
        except ToolError as exc:
            tool_result = ToolResult(name=decision.tool, success=False, data={"error": str(exc)})
            reply_text = self._fail_safe_response(
                request,
                session=session,
                language=language,
                bilingual=request.bilingual,
                reason=str(exc),
            )
            session.add_turn(role="tool", content=str(exc), tool_name=decision.tool)
        else:
            session.add_turn(role="tool", content=str(tool_result.data), tool_name=tool_result.name)

        session.add_turn(role="assistant", content=reply_text)
        session.greeting_sent = True

        return ConversationResponse(
            session_id=request.session_id,
            reply=reply_text,
            decision=decision.decision,
            tool=ToolPayload(name=tool_result.name, success=tool_result.success, data=tool_result.data),
            language=language,
            memory=session.turns,
            trace_id=trace_id,
        )

    def _decide(self, request: ConversationRequest) -> PolicyDecision:
        utterance = request.text.lower()
        if any(keyword in utterance for keyword in ["schedule", "book", "install", "appointment"]):
            return PolicyDecision(decision="schedule_service", tool=self.scheduler_tool.name)
        if any(keyword in utterance for keyword in ["notify", "remind", "message"]):
            return PolicyDecision(decision="create_notification", tool=self.notifier_tool.name)
        return PolicyDecision(decision="retrieve_context", tool=self.rag_tool.name)

    def _execute(self, decision: PolicyDecision, request: ConversationRequest, session: SessionMemory) -> ToolResult:
        if decision.tool == self.scheduler_tool.name:
            return self.scheduler_tool.run(request_text=request.text)
        if decision.tool == self.notifier_tool.name:
            return self.notifier_tool.run(request_text=request.text, language=session.language)
        if decision.tool == self.rag_tool.name:
            memory_slice = session.recent_user_messages()
            return self.rag_tool.run(query=request.text, memory=memory_slice)
        raise ToolError(f"Unknown tool '{decision.tool}'")

    def _compose_reply(
        self,
        decision: PolicyDecision,
        tool_result: ToolResult,
        request: ConversationRequest,
        session: SessionMemory,
        *,
        language: str,
        bilingual: bool,
    ) -> str:
        if decision.tool == self.scheduler_tool.name and tool_result.success:
            slots = tool_result.data.get("slots", [])
            if tool_result.data.get("reason") == "out_of_area":
                distance = tool_result.data.get("distance_km")
                english = (
                    "It looks like you're outside our service radius. I've noted your details for a follow-up."
                )
                if distance:
                    english += f" The nearest team is about {distance} km away."
            elif slots:
                english = "Here are the booking options for next week: " + ", ".join(slots)
            else:
                english = "I have availability details ready once you're within our service area."
        elif decision.tool == self.notifier_tool.name and tool_result.success:
            confirmation = tool_result.data
            english = (
                "I've queued a notification via {channel}. You'll receive a confirmation shortly."
            ).format(channel=confirmation.get("channel", "sms"))
        else:
            snippets = tool_result.data.get("snippets", [])
            english = "Context I found: " + " | ".join(snippets)
        bundle = build_prompt(
            request.tone,
            english,
            bilingual=bilingual,
            primary_language=language,
        )
        return format_bilingual_message(
            bundle,
            bilingual=bilingual,
            primary_language=language,
            include_greeting=not session.greeting_sent,
        )

    def _fail_safe_response(
        self,
        request: ConversationRequest,
        *,
        session: SessionMemory,
        language: str,
        bilingual: bool,
        reason: str | None = None,
    ) -> str:
        english = (
            "Our calendar is temporarily unavailable. I'm taking a note for our team to follow up soon."
            if reason and "calendar" in reason.lower()
            else "I couldn't activate my tools right now, but I've taken a message for our team to follow up."
        )
        bundle = build_prompt(
            request.tone,
            english,
            bilingual=bilingual,
            primary_language=language,
        )
        return format_bilingual_message(
            bundle,
            bilingual=bilingual,
            primary_language=language,
            include_greeting=not session.greeting_sent,
        )

"""Tool implementations invoked by the policy engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
import json
import os
import re
from typing import Dict, Iterable, List, Protocol
from urllib import error as urllib_error
from urllib import request as urllib_request


class ToolError(RuntimeError):
    """Raised when a tool cannot complete its work."""


@dataclass
class ToolResult:
    """Normalized payload returned from any tool invocation."""

    name: str
    success: bool
    data: Dict


class Tool(Protocol):
    """Protocol shared across orchestrator tools."""

    name: str

    def run(self, **kwargs) -> ToolResult:  # pragma: no cover - protocol method signature
        ...


class RetrievalAugmentedGenerator:
    """Returns contextual snippets relevant to the user prompt."""

    name = "rag"

    def __init__(self) -> None:
        self.knowledge_base = {
            "water heater": "Licensed plumbers handle water heater installations and typically need a 2-hour window.",
            "next week": "Next week has availability on Tuesday and Thursday mornings.",
        }

    def run(self, query: str, memory: Iterable[str]) -> ToolResult:
        snippets: List[str] = []
        for key, value in self.knowledge_base.items():
            if key in query.lower():
                snippets.append(value)
        snippets.extend(memory)
        if not snippets:
            snippets.append("No additional context was retrieved.")
        return ToolResult(name=self.name, success=True, data={"snippets": snippets})


class SchedulerTool:
    """Provides booking availability suggestions."""

    name = "scheduler"

    def __init__(self, calendar_url: str | None = None) -> None:
        self.calendar_url = calendar_url or os.getenv("CALENDAR_SERVICE_URL")
        self.mapping_url = os.getenv("MAPPING_SERVICE_URL")

    def run(self, request_text: str) -> ToolResult:
        if "install" not in request_text.lower() and "book" not in request_text.lower():
            raise ToolError("Scheduler only handles booking intents.")
        lowered = request_text.lower()
        if "message only" in lowered or "calendar down" in lowered or "take a message" in lowered:
            raise ToolError("Calendar service unavailable")
        self._ensure_calendar_available()
        service_area = self._interpret_service_area(request_text)
        if service_area and not service_area["within_radius"]:
            distance = round(service_area.get("distance_km", 0.0), 2)
            return ToolResult(
                name=self.name,
                success=True,
                data={
                    "slots": [],
                    "reason": "out_of_area",
                    "distance_km": distance,
                    "message": "Caller is outside the service radius.",
                },
            )
        today = datetime.utcnow()
        days_until_monday = (7 - today.weekday()) % 7 or 7
        start_date = (today + timedelta(days=days_until_monday)).date()
        slots = []
        for offset in (0, 2, 4):
            slot_date = start_date + timedelta(days=offset)
            slot_dt = datetime.combine(slot_date, time(hour=9))
            slots.append(slot_dt.strftime("%A %b %d at %I:%M %p"))
        return ToolResult(
            name=self.name,
            success=True,
            data={
                "slots": slots,
                "note": "Technician requires someone on site during the 2-hour window.",
            },
        )

    def _ensure_calendar_available(self) -> None:
        if not self.calendar_url:
            return
        health_url = self.calendar_url.rstrip("/") + "/health"
        try:
            with urllib_request.urlopen(health_url, timeout=1) as response:  # pragma: no cover - network I/O
                if getattr(response, "status", 200) >= 500:
                    raise ToolError("Calendar service unavailable")
        except urllib_error.URLError as exc:  # pragma: no cover - network I/O
            raise ToolError("Calendar service unavailable") from exc

    def _interpret_service_area(self, request_text: str) -> Dict[str, float] | None:
        coords = self._extract_coordinates(request_text)
        if coords and self.mapping_url:
            url = self.mapping_url.rstrip("/") + "/v1/service-area/check"
            payload = json.dumps({"location": {"lat": coords[0], "lng": coords[1]}}).encode("utf-8")
            req = urllib_request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            try:  # pragma: no cover - network I/O
                with urllib_request.urlopen(req, timeout=1) as response:
                    body = response.read().decode("utf-8")
                    data = json.loads(body)
                    return {
                        "within_radius": bool(data.get("within_radius", False)),
                        "distance_km": float(data.get("distance_km", 0.0)),
                    }
            except urllib_error.URLError:
                return None
        lowered = request_text.lower()
        if "out of area" in lowered or "outside service" in lowered:
            return {"within_radius": False, "distance_km": 999.0}
        return None

    def _extract_coordinates(self, text: str) -> tuple[float, float] | None:
        match = re.search(r"(-?\d+(?:\.\d+)?)[,\s]+(-?\d+(?:\.\d+)?)", text)
        if not match:
            return None
        try:
            return float(match.group(1)), float(match.group(2))
        except ValueError:
            return None


class NotifierTool:
    """Creates a follow-up notification request."""

    name = "notifier"

    def run(self, request_text: str, channel: str = "sms", language: str = "en") -> ToolResult:
        if channel not in {"sms", "email"}:
            raise ToolError("Unsupported notification channel.")
        language = language if language in {"en", "es"} else "en"
        localized_messages = {
            "en": "I've queued a {channel} follow-up. You'll receive a confirmation shortly.",
            "es": "He programado un mensaje por {channel}. Recibirá una confirmación pronto.",
        }
        confirmation = {
            "channel": channel,
            "status": "queued",
            "summary": request_text,
            "language": language,
            "message": localized_messages[language].format(channel=channel),
        }
        return ToolResult(name=self.name, success=True, data=confirmation)

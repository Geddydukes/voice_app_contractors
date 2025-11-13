from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, List
from uuid import uuid4

from .config import CalendarConfig
from .models import CalendarEvent, Coordinate


@dataclass(slots=True)
class InMemoryCalendarStore:
    events: Dict[str, CalendarEvent] = field(default_factory=dict)

    def list_events(self) -> List[CalendarEvent]:
        return sorted(self.events.values(), key=lambda event: event.start)

    def events_between(self, start: datetime, end: datetime) -> List[CalendarEvent]:
        return [event for event in self.list_events() if not (event.end <= start or event.start >= end)]

    def events_for_day(self, day: date) -> List[CalendarEvent]:
        start = datetime.combine(day, time.min)
        end = datetime.combine(day + timedelta(days=1), time.min)
        return self.events_between(start, end)

    def add_event(self, event: CalendarEvent) -> CalendarEvent:
        self.events[event.id] = event
        return event

    def create_event(
        self,
        *,
        summary: str,
        start: datetime,
        end: datetime,
        location: Coordinate,
        customer_name: str | None = None,
        metadata: Dict[str, object] | None = None,
    ) -> CalendarEvent:
        event = CalendarEvent(
            id=str(uuid4()),
            summary=summary,
            start=start,
            end=end,
            location=location,
            customer_name=customer_name,
            metadata=metadata or {},
        )
        return self.add_event(event)


def seed_demo_events(store: InMemoryCalendarStore, config: CalendarConfig) -> None:
    if store.events:
        return

    today = datetime.utcnow().date()
    day_one = today + timedelta(days=1)
    day_two = today + timedelta(days=2)

    base_lat = config.base_lat
    base_lng = config.base_lng

    store.create_event(
        summary="Heat pump consultation",
        start=datetime.combine(day_one, time(hour=9, minute=0)),
        end=datetime.combine(day_one, time(hour=10, minute=30)),
        location=Coordinate(lat=base_lat + 0.05, lng=base_lng - 0.02),
        customer_name="Jordan Smith",
        metadata={"address": "1234 5th Ave"},
    )
    store.create_event(
        summary="Water heater replacement",
        start=datetime.combine(day_one, time(hour=13, minute=0)),
        end=datetime.combine(day_one, time(hour=14, minute=30)),
        location=Coordinate(lat=base_lat - 0.07, lng=base_lng + 0.03),
        customer_name="Priya Patel",
        metadata={"address": "880 Market St"},
    )
    store.create_event(
        summary="Solar consultation",
        start=datetime.combine(day_two, time(hour=11, minute=0)),
        end=datetime.combine(day_two, time(hour=12, minute=0)),
        location=Coordinate(lat=base_lat + 0.02, lng=base_lng + 0.04),
        customer_name="Miguel Torres",
        metadata={"address": "25 Union St"},
    )

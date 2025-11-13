from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from typing import Iterable, List

from .config import CalendarConfig
from .mapping_client import MappingClient
from .models import (
    CalendarEvent,
    CandidateSlot,
    Coordinate,
    FreeBusyResponse,
    FreeBusySlot,
    ScheduleBookRequest,
    ScheduleBookResponse,
    ScheduleFindRequest,
    ScheduleFindResponse,
)
from .oauth import OAuthClient
from .storage import InMemoryCalendarStore


@dataclass(slots=True)
class Scheduler:
    config: CalendarConfig
    store: InMemoryCalendarStore
    mapping: MappingClient
    oauth: OAuthClient

    def free_busy(self, start: date, end: date) -> FreeBusyResponse:
        start_dt = datetime.combine(start, time.min)
        end_dt = datetime.combine(end + timedelta(days=1), time.min)
        blocks: List[FreeBusySlot] = [
            FreeBusySlot(
                start=event.start,
                end=event.end,
                summary=event.summary,
                location=event.location,
            )
            for event in self.store.events_between(start_dt, end_dt)
        ]
        return FreeBusyResponse(resource=self.config.resource_email, blocks=blocks)

    def find_slots(self, request: ScheduleFindRequest) -> ScheduleFindResponse:
        self.oauth.current_token()  # ensure the token is current before querying

        slots: List[CandidateSlot] = []
        for day in _daterange(request.start_date, request.end_date):
            slots.extend(self._slots_for_day(day, request))

        slots.sort(key=lambda slot: slot.start)
        return ScheduleFindResponse(
            customer_name=request.customer_name,
            service_address=request.service_address,
            requested_duration_minutes=request.duration_minutes,
            slots=slots,
        )

    def book(self, request: ScheduleBookRequest) -> ScheduleBookResponse:
        availability = self.find_slots(request)
        matching_slot = next((slot for slot in availability.slots if slot.start == request.slot_start), None)
        if matching_slot is None:
            raise ValueError("Requested slot is no longer available")
        if not matching_slot.service_area_ok:
            raise ValueError("Requested slot is outside the service area")

        event = self.store.create_event(
            summary=f"Service for {request.customer_name}",
            start=matching_slot.start,
            end=matching_slot.end,
            location=request.location,
            customer_name=request.customer_name,
            metadata={
                "address": request.service_address,
                "phone": request.customer_phone,
            },
        )
        return ScheduleBookResponse(
            event=event,
            travel_before_minutes=matching_slot.travel_before_minutes,
            travel_after_minutes=matching_slot.travel_after_minutes,
        )

    def _slots_for_day(self, day: date, request: ScheduleFindRequest) -> List[CandidateSlot]:
        workday_start = datetime.combine(day, self.config.workday_start)
        workday_end = datetime.combine(day, self.config.workday_end)
        if workday_end <= workday_start:
            return []

        events = self.store.events_for_day(day)
        base_location = Coordinate(lat=self.config.base_lat, lng=self.config.base_lng)

        # Add boundary events to simplify travel calculations.
        boundary_start = CalendarEvent(
            id="__start__",
            summary="Depot",
            start=workday_start,
            end=workday_start,
            location=base_location,
        )
        boundary_end = CalendarEvent(
            id="__end__",
            summary="Depot",
            start=workday_end,
            end=workday_end,
            location=base_location,
        )
        ordered_events = [boundary_start, *events, boundary_end]

        service_area_ok = self.mapping.within_service_area(request.location)
        if not service_area_ok:
            return []

        slots: List[CandidateSlot] = []
        for prev_event, next_event in pairwise(ordered_events):
            window_start = max(prev_event.end, workday_start)
            window_end = min(next_event.start, workday_end)
            if window_end <= window_start:
                continue

            travel_before = self.mapping.travel_time(prev_event.location, request.location)
            travel_after = self.mapping.travel_time(request.location, next_event.location)

            available_start = window_start + timedelta(minutes=travel_before.duration_minutes)
            latest_start = window_end - timedelta(
                minutes=request.duration_minutes + travel_after.duration_minutes
            )

            if request.time_window_start:
                available_start = max(
                    available_start,
                    datetime.combine(day, request.time_window_start),
                )
            if request.time_window_end:
                latest_start = min(
                    latest_start,
                    datetime.combine(day, request.time_window_end) - timedelta(minutes=request.duration_minutes),
                )

            if latest_start < available_start:
                continue

            slot_start = _round_up(available_start, self.config.slot_interval_minutes)
            while slot_start <= latest_start:
                slot_end = slot_start + timedelta(minutes=request.duration_minutes)
                slots.append(
                    CandidateSlot(
                        start=slot_start,
                        end=slot_end,
                        travel_before_minutes=int(round(travel_before.duration_minutes)),
                        travel_after_minutes=int(round(travel_after.duration_minutes)),
                        service_area_ok=True,
                    )
                )
                slot_start += timedelta(minutes=self.config.slot_interval_minutes)

        return slots


def _round_up(dt: datetime, interval_minutes: int) -> datetime:
    total_minutes = dt.hour * 60 + dt.minute
    remainder = total_minutes % interval_minutes
    if remainder == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt.replace(second=0, microsecond=0)
    delta_minutes = (interval_minutes - remainder) % interval_minutes
    if delta_minutes == 0:
        delta_minutes = interval_minutes
    rounded = dt + timedelta(minutes=delta_minutes)
    return rounded.replace(second=0, microsecond=0)


def _daterange(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)

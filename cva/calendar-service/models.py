from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Coordinate(BaseModel):
    lat: float = Field(..., description="Latitude in decimal degrees")
    lng: float = Field(..., description="Longitude in decimal degrees")

    @field_validator("lat")
    @classmethod
    def _validate_lat(cls, value: float) -> float:
        if not -90 <= value <= 90:
            raise ValueError("latitude must be between -90 and 90 degrees")
        return value

    @field_validator("lng")
    @classmethod
    def _validate_lng(cls, value: float) -> float:
        if not -180 <= value <= 180:
            raise ValueError("longitude must be between -180 and 180 degrees")
        return value

    def as_tuple(self) -> tuple[float, float]:
        return (self.lat, self.lng)


class OAuthToken(BaseModel):
    access_token: str
    expires_at: datetime

    def is_expired(self, *, buffer_seconds: int = 30) -> bool:
        return datetime.utcnow() + timedelta(seconds=buffer_seconds) >= self.expires_at


class CalendarEvent(BaseModel):
    id: str
    summary: str
    start: datetime
    end: datetime
    location: Coordinate
    customer_name: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_time_order(self) -> "CalendarEvent":
        if self.end <= self.start:
            raise ValueError("event end must be after start")
        return self


class FreeBusySlot(BaseModel):
    start: datetime
    end: datetime
    summary: str
    location: Coordinate


class ScheduleFindRequest(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = Field(default=None, description="Optional phone number to attach to the booking")
    service_address: str
    location: Coordinate
    duration_minutes: int = Field(default=60, gt=0, le=6 * 60)
    start_date: date
    end_date: date
    time_window_start: Optional[time] = None
    time_window_end: Optional[time] = None

    @model_validator(mode="after")
    def _validate_dates(self) -> "ScheduleFindRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if self.time_window_start and self.time_window_end:
            if self.time_window_end <= self.time_window_start:
                raise ValueError("time_window_end must be after time_window_start")
        return self


class CandidateSlot(BaseModel):
    start: datetime
    end: datetime
    travel_before_minutes: int
    travel_after_minutes: int
    service_area_ok: bool


class ScheduleFindResponse(BaseModel):
    customer_name: str
    service_address: str
    requested_duration_minutes: int
    slots: List[CandidateSlot]


class ScheduleBookRequest(ScheduleFindRequest):
    slot_start: datetime

    @model_validator(mode="after")
    def _validate_slot(self) -> "ScheduleBookRequest":
        slot_day = self.slot_start.date()
        if slot_day < self.start_date or slot_day > self.end_date:
            raise ValueError("slot_start must fall within the requested window")
        return self


class ScheduleBookResponse(BaseModel):
    event: CalendarEvent
    travel_before_minutes: int
    travel_after_minutes: int


class FreeBusyResponse(BaseModel):
    resource: str
    blocks: List[FreeBusySlot]


class OAuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int

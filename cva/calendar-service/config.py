from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time


@dataclass(slots=True)
class CalendarConfig:
    client_id: str
    client_secret: str
    refresh_token: str
    resource_email: str
    base_lat: float
    base_lng: float
    service_radius_km: float
    travel_speed_kmph: float
    workday_start: time
    workday_end: time
    slot_interval_minutes: int
    mapping_service_url: str | None

    @classmethod
    def load(cls) -> "CalendarConfig":
        def _get_time(var: str, default: int) -> time:
            raw = os.getenv(var)
            hour = int(raw) if raw is not None else default
            if not 0 <= hour <= 23:
                raise ValueError(f"{var} must be between 0 and 23")
            return time(hour=hour)

        def _get_positive_int(var: str, default: int) -> int:
            raw = os.getenv(var)
            value = int(raw) if raw is not None else default
            if value <= 0:
                raise ValueError(f"{var} must be positive")
            return value

        return cls(
            client_id=os.getenv("CALENDAR_OAUTH_CLIENT_ID", "demo-client"),
            client_secret=os.getenv("CALENDAR_OAUTH_CLIENT_SECRET", "demo-secret"),
            refresh_token=os.getenv("CALENDAR_OAUTH_REFRESH_TOKEN", "demo-refresh-token"),
            resource_email=os.getenv("CALENDAR_RESOURCE_EMAIL", "calendar@example.com"),
            base_lat=float(os.getenv("CALENDAR_BASE_LAT", "47.6062")),
            base_lng=float(os.getenv("CALENDAR_BASE_LNG", "-122.3321")),
            service_radius_km=float(os.getenv("CALENDAR_SERVICE_RADIUS_KM", "45")),
            travel_speed_kmph=float(os.getenv("CALENDAR_TRAVEL_SPEED_KMPH", "48")),
            workday_start=_get_time("CALENDAR_WORKDAY_START_HOUR", 8),
            workday_end=_get_time("CALENDAR_WORKDAY_END_HOUR", 18),
            slot_interval_minutes=_get_positive_int("CALENDAR_SLOT_INTERVAL_MINUTES", 30),
            mapping_service_url=os.getenv("MAPPING_SERVICE_URL"),
        )

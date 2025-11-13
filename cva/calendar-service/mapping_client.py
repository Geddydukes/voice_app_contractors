from __future__ import annotations

import math
from dataclasses import dataclass

try:
    import httpx
except ImportError:  # pragma: no cover - optional dependency
    httpx = None

from .config import CalendarConfig
from .models import Coordinate


@dataclass(slots=True)
class TravelEstimate:
    distance_km: float
    duration_minutes: float


class MappingClient:
    def __init__(self, config: CalendarConfig) -> None:
        self._config = config
        if httpx is not None and config.mapping_service_url:
            self._client = httpx.Client(timeout=5.0)
        else:
            self._client = None

    def distance_from_base(self, location: Coordinate) -> TravelEstimate:
        base_coord = Coordinate(lat=self._config.base_lat, lng=self._config.base_lng)
        return self.travel_time(base_coord, location)

    def travel_time(self, origin: Coordinate, destination: Coordinate) -> TravelEstimate:
        if self._client is not None and self._config.mapping_service_url and httpx is not None:
            try:
                response = self._client.post(
                    f"{self._config.mapping_service_url.rstrip('/')}/v1/routes/matrix",
                    json={
                        "origins": [origin.model_dump()],
                        "destinations": [destination.model_dump()],
                        "speed_kmph": self._config.travel_speed_kmph,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                row = payload["matrix"][0]
                return TravelEstimate(
                    distance_km=row["distances_km"][0],
                    duration_minutes=row["durations_minutes"][0],
                )
            except Exception:
                # Fall back to local calculation if the mapping service is unreachable.
                pass
        return _local_estimate(origin, destination, self._config.travel_speed_kmph)

    def within_service_area(self, location: Coordinate) -> bool:
        estimate = self.distance_from_base(location)
        return estimate.distance_km <= self._config.service_radius_km


def _local_estimate(origin: Coordinate, destination: Coordinate, speed_kmph: float) -> TravelEstimate:
    distance_km = _haversine(origin.as_tuple(), destination.as_tuple())
    travel_hours = distance_km / max(speed_kmph, 1)
    return TravelEstimate(distance_km=distance_km, duration_minutes=travel_hours * 60)


def _haversine(origin: tuple[float, float], destination: tuple[float, float]) -> float:
    lat1, lon1 = origin
    lat2, lon2 = destination
    radius = 6371.0

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c

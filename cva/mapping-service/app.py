from __future__ import annotations

import math
import os
from typing import List

from fastapi import FastAPI, HTTPException

from shared.observability import instrument_app
from pydantic import BaseModel, Field, field_validator

app = FastAPI(title="Mapping Service")
logger = instrument_app(app, "mapping-service")


def _haversine_km(origin: tuple[float, float], destination: tuple[float, float]) -> float:
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


class RouteMatrixRequest(BaseModel):
    origins: List[Coordinate]
    destinations: List[Coordinate]
    speed_kmph: float | None = Field(
        default=None,
        description="Optional override for the assumed travel speed in km/h.",
    )

    @field_validator("origins", "destinations")
    @classmethod
    def _ensure_non_empty(cls, value: List[Coordinate]) -> List[Coordinate]:
        if not value:
            raise ValueError("at least one coordinate is required")
        return value


class RouteMatrixRow(BaseModel):
    distances_km: List[float]
    durations_minutes: List[float]


class RouteMatrixResponse(BaseModel):
    matrix: List[RouteMatrixRow]
    assumed_speed_kmph: float


class ServiceAreaRequest(BaseModel):
    location: Coordinate


class ServiceAreaResponse(BaseModel):
    within_radius: bool
    distance_km: float
    radius_km: float
    base: Coordinate


DEFAULT_SPEED_KMPH = float(os.getenv("CALENDAR_TRAVEL_SPEED_KMPH", "45"))
BASE_LAT = float(os.getenv("CALENDAR_BASE_LAT", "47.6062"))
BASE_LNG = float(os.getenv("CALENDAR_BASE_LNG", "-122.3321"))
SERVICE_RADIUS_KM = float(os.getenv("CALENDAR_SERVICE_RADIUS_KM", "45"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mapping"}


@app.post("/v1/routes/matrix", response_model=RouteMatrixResponse)
def route_matrix(request: RouteMatrixRequest) -> RouteMatrixResponse:
    speed = request.speed_kmph or DEFAULT_SPEED_KMPH
    if speed <= 0:
        raise HTTPException(status_code=400, detail="Speed must be positive")

    matrix: List[RouteMatrixRow] = []
    for origin in request.origins:
        distances: List[float] = []
        durations: List[float] = []
        for destination in request.destinations:
            distance_km = _haversine_km(origin.as_tuple(), destination.as_tuple())
            travel_hours = distance_km / speed
            distances.append(round(distance_km, 3))
            durations.append(round(travel_hours * 60, 1))
        matrix.append(RouteMatrixRow(distances_km=distances, durations_minutes=durations))

    response = RouteMatrixResponse(matrix=matrix, assumed_speed_kmph=speed)
    logger.info(
        "Route matrix calculated origins=%s destinations=%s",
        len(request.origins),
        len(request.destinations),
    )
    return response


@app.post("/v1/service-area/check", response_model=ServiceAreaResponse)
def service_area_check(request: ServiceAreaRequest) -> ServiceAreaResponse:
    distance_km = _haversine_km((BASE_LAT, BASE_LNG), request.location.as_tuple())
    response = ServiceAreaResponse(
        within_radius=distance_km <= SERVICE_RADIUS_KM,
        distance_km=round(distance_km, 3),
        radius_km=SERVICE_RADIUS_KM,
        base=Coordinate(lat=BASE_LAT, lng=BASE_LNG),
    )
    logger.info(
        "Service area check distance_km=%.2f within=%s",
        response.distance_km,
        response.within_radius,
    )
    return response

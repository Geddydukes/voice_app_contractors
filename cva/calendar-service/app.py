from datetime import date

from fastapi import FastAPI, HTTPException

from shared.observability import instrument_app

from .config import CalendarConfig
from .mapping_client import MappingClient
from .models import (
    OAuthTokenResponse,
    ScheduleBookRequest,
    ScheduleBookResponse,
    ScheduleFindRequest,
    ScheduleFindResponse,
)
from .oauth import OAuthClient
from .scheduler import Scheduler
from .storage import InMemoryCalendarStore, seed_demo_events

app = FastAPI(title="Calendar Service")
logger = instrument_app(app, "calendar-service")

config = CalendarConfig.load()
store = InMemoryCalendarStore()
seed_demo_events(store, config)
mapping_client = MappingClient(config)
oauth_client = OAuthClient(config)
scheduler = Scheduler(
    config=config,
    store=store,
    mapping=mapping_client,
    oauth=oauth_client,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "calendar"}


@app.get("/v1/oauth/token", response_model=OAuthTokenResponse)
def issue_token() -> OAuthTokenResponse:
    token = oauth_client.current_token()
    return OAuthTokenResponse(access_token=token.access_token, expires_in=3600)


@app.get("/v1/calendar/free-busy")
def free_busy(start: date, end: date):
    if end < start:
        raise HTTPException(status_code=400, detail="end must be on or after start")
    return scheduler.free_busy(start, end)


@app.post("/v1/schedule/find", response_model=ScheduleFindResponse)
def find_schedule(request: ScheduleFindRequest) -> ScheduleFindResponse:
    try:
        response = scheduler.find_slots(request)
    except ValueError as exc:  # bubble up validation issues as HTTP errors
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info("Slots calculated count=%s", len(response.slots))
    return response


@app.post("/v1/schedule/book", response_model=ScheduleBookResponse)
def book_schedule(request: ScheduleBookRequest) -> ScheduleBookResponse:
    try:
        response = scheduler.book(request)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info("Booking confirmed reference=%s", response.confirmation.reference_id)
    return response

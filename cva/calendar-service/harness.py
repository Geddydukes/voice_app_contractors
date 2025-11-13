from __future__ import annotations

import argparse
import importlib.util
import sys
import types
from datetime import date, timedelta
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
PACKAGE_NAME = "calendar_service"


if __package__ is None:
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(MODULE_DIR)]
    sys.modules[PACKAGE_NAME] = package

    def _load(name: str):
        spec = importlib.util.spec_from_file_location(name, MODULE_DIR / f"{name.split('.')[-1]}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    config = _load(f"{PACKAGE_NAME}.config")
    mapping_client = _load(f"{PACKAGE_NAME}.mapping_client")
    models = _load(f"{PACKAGE_NAME}.models")
    oauth = _load(f"{PACKAGE_NAME}.oauth")
    scheduler_mod = _load(f"{PACKAGE_NAME}.scheduler")
    storage_mod = _load(f"{PACKAGE_NAME}.storage")
else:
    from . import config, mapping_client, models, oauth, scheduler as scheduler_mod, storage as storage_mod

CalendarConfig = config.CalendarConfig
MappingClient = mapping_client.MappingClient
Coordinate = models.Coordinate
ScheduleBookRequest = models.ScheduleBookRequest
ScheduleFindRequest = models.ScheduleFindRequest
OAuthClient = oauth.OAuthClient
Scheduler = scheduler_mod.Scheduler
InMemoryCalendarStore = storage_mod.InMemoryCalendarStore
seed_demo_events = storage_mod.seed_demo_events


def build_scheduler() -> Scheduler:
    cfg = CalendarConfig.load()
    store = InMemoryCalendarStore()
    seed_demo_events(store, cfg)
    mapping = MappingClient(cfg)
    oauth_client = OAuthClient(cfg)
    return Scheduler(config=cfg, store=store, mapping=mapping, oauth=oauth_client)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local scheduling scenarios")
    parser.add_argument("address", nargs="?", default="1501 4th Ave", help="Service address")
    parser.add_argument("lat", nargs="?", type=float, default=47.6097, help="Latitude for the job site")
    parser.add_argument("lng", nargs="?", type=float, default=-122.3331, help="Longitude for the job site")
    parser.add_argument("duration", nargs="?", type=int, default=90, help="Duration minutes")
    parser.add_argument("days", nargs="?", type=int, default=2, help="Days from today to search")
    parser.add_argument("--book", action="store_true", help="Book the first available slot")
    args = parser.parse_args()

    scheduler = build_scheduler()

    start_day = date.today()
    end_day = start_day + timedelta(days=args.days)

    request = ScheduleFindRequest(
        customer_name="CLI Harness",
        customer_phone="555-0100",
        service_address=args.address,
        location=Coordinate(lat=args.lat, lng=args.lng),
        duration_minutes=args.duration,
        start_date=start_day,
        end_date=end_day,
    )

    response = scheduler.find_slots(request)
    if not response.slots:
        print("No availability found.")
        return

    print("Available slots:")
    for slot in response.slots:
        print(
            f"  - {slot.start.isoformat()} -> {slot.end.isoformat()} (travel before: {slot.travel_before_minutes}m, after: {slot.travel_after_minutes}m)"
        )

    if args.book:
        chosen = response.slots[0]
        book_request = ScheduleBookRequest(**request.model_dump(), slot_start=chosen.start)
        confirmation = scheduler.book(book_request)
        print("\nBooked appointment:")
        print(f"  id: {confirmation.event.id}")
        print(f"  start: {confirmation.event.start}")
        print(f"  end: {confirmation.event.end}")
        print(f"  travel (before/after): {confirmation.travel_before_minutes}m/{confirmation.travel_after_minutes}m")


if __name__ == "__main__":
    main()

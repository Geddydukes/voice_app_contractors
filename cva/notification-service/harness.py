"""Local harness to preview booking notification payloads."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta

from app import (
    BookingNotificationRequest,
    BookingNotificationResponse,
    _lead_store,
    send_booking_notifications,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate booking notifications for a demo lead")
    parser.add_argument("--contractor", default="Riverbend Plumbing", help="Contractor name")
    parser.add_argument("--caller", default="Jamie Rivera", help="Caller name")
    parser.add_argument("--phone", default="555-0101", help="Caller phone number")
    parser.add_argument("--email", default="jamie@example.com", help="Caller email")
    parser.add_argument("--language", default="en", help="Language for rendered notifications (en or es)")
    args = parser.parse_args()

    lead = _lead_store.create_lead(
        caller_name=args.caller,
        caller_phone=args.phone,
        caller_email=args.email,
        transcript="Need help installing a new water heater next week.",
        summary="Caller needs water heater installation",
    )

    request = BookingNotificationRequest(
        lead_id=lead["id"],
        contractor_name=args.contractor,
        contractor_phone="555-0200",
        contractor_email="dispatch@riverbendplumbing.com",
        caller_name=args.caller,
        caller_phone=args.phone,
        caller_email=args.email,
        appointment_time=datetime.utcnow() + timedelta(days=2),
        service_summary="Water heater installation",
        service_address="1501 4th Ave, Seattle, WA",
        language=args.language,
    )
    response: BookingNotificationResponse = send_booking_notifications(request)
    print(json.dumps(response.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    main()

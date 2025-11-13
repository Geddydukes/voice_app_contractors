"""Notification service routes for booking confirmations."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator

from shared.leads import LeadNotFoundError, LeadStore
from shared.observability import instrument_app, sanitize_value
from shared.notifications import render_booking_notifications

app = FastAPI(title="Notification Service")
logger = instrument_app(app, "notification-service")

_lead_store = LeadStore()
_sender_name = os.getenv("NOTIFICATION_SENDER_NAME", "Contractor Voice Assistant")
_sender_email = os.getenv("NOTIFICATION_SENDER", "notifications@example.com")
_sender_phone = os.getenv("NOTIFICATION_SENDER_PHONE", "+15555550100")


class BookingNotificationRequest(BaseModel):
    lead_id: int = Field(..., description="Lead identifier to attach notifications to")
    contractor_name: str
    contractor_phone: str | None = None
    contractor_email: EmailStr | None = None
    caller_name: str
    caller_phone: str
    caller_email: EmailStr | None = None
    appointment_time: datetime
    service_summary: str
    service_address: str
    language: str = Field(default="en", description="Language code for rendered notifications")


class DispatchedMessage(BaseModel):
    id: int
    audience: str
    channel: str
    recipient: str
    template: str
    body: str
    status: str | None = None
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _parse_datetime(cls, value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)


class BookingNotificationResponse(BaseModel):
    messages: List[DispatchedMessage]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "notification"}


@app.post("/v1/notify/booking", response_model=BookingNotificationResponse)
def send_booking_notifications(request: BookingNotificationRequest) -> BookingNotificationResponse:
    try:
        _lead_store.update_appointment(request.lead_id, request.appointment_time)
    except LeadNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    messages = render_booking_notifications(
        contractor_name=request.contractor_name,
        contractor_phone=request.contractor_phone,
        contractor_email=request.contractor_email,
        caller_name=request.caller_name,
        caller_phone=request.caller_phone,
        caller_email=request.caller_email,
        appointment_time=request.appointment_time,
        service_summary=request.service_summary,
        service_address=request.service_address,
        sender_name=_sender_name,
        sender_phone=_sender_phone,
        sender_email=_sender_email,
        language=request.language,
    )

    dispatched: List[DispatchedMessage] = []
    for message in messages:
        metadata: Dict[str, Any] = {
            "audience": message.audience,
            "subject": message.subject,
            "context": message.metadata,
            "language": message.language,
        }
        record = _lead_store.record_message(
            request.lead_id,
            direction="outbound",
            channel=message.channel,
            recipient=message.recipient,
            body=message.body,
            template=message.template,
            status="sent",
            metadata=metadata,
        )
        dispatched.append(
            DispatchedMessage(
                id=record.id,
                audience=message.audience,
                channel=record.channel,
                recipient=record.recipient,
                template=record.template,
                body=record.body,
                status=record.status,
                created_at=record.created_at,
            )
        )

    logger.info(
        "Notifications dispatched lead=%s count=%s to=%s",
        request.lead_id,
        len(dispatched),
        sanitize_value(request.caller_phone),
    )
    return BookingNotificationResponse(messages=dispatched)

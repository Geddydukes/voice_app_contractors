"""Template rendering utilities for outbound notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List

from shared.leads import format_iso_timestamp


@dataclass(frozen=True)
class NotificationMessage:
    """Represents a rendered notification ready for dispatch."""

    audience: str
    channel: str
    recipient: str
    subject: str | None
    body: str
    template: str
    metadata: dict
    language: str


def render_booking_notifications(
    *,
    contractor_name: str,
    contractor_phone: str | None,
    contractor_email: str | None,
    caller_name: str,
    caller_phone: str,
    caller_email: str | None,
    appointment_time: datetime,
    service_summary: str,
    service_address: str,
    sender_name: str,
    sender_phone: str | None,
    sender_email: str | None,
    language: str = "en",
) -> List[NotificationMessage]:
    """Build SMS and email notifications for a confirmed booking."""

    pretty_time = appointment_time.strftime("%A, %B %d at %I:%M %p %Z").strip()
    if not appointment_time.tzinfo:
        # ``strftime`` above omits timezone for naive datetimes, fallback to ISO representation.
        pretty_time = appointment_time.strftime("%A, %B %d at %I:%M %p") + " UTC"

    messages: List[NotificationMessage] = []

    language = language if language in {"en", "es"} else "en"
    contractor_language = language
    caller_language = language

    contractor_context = {
        "appointment_time": format_iso_timestamp(appointment_time),
        "service_summary": service_summary,
        "service_address": service_address,
    }
    caller_context = contractor_context | {"contractor_name": contractor_name}

    contractor_sms_body = (
        f"New booking for {caller_name} on {pretty_time}. "
        f"Job location: {service_address}. Details: {service_summary}."
    )
    contractor_email_lines = [
        f"Hi {contractor_name},",
        "",
        f"You're scheduled to assist {caller_name} on {pretty_time}.",
        f"Service summary: {service_summary}.",
        f"Job location: {service_address}.",
    ]
    caller_sms_body = (
        f"Hi {caller_name}, your appointment with {contractor_name} is set for {pretty_time}. "
        f"We'll see you at {service_address}."
    )
    caller_email_lines = [
        f"Hello {caller_name},",
        "",
        f"Thanks for booking with {contractor_name}!",
        f"Appointment time: {pretty_time}.",
        f"Location: {service_address}.",
        f"Service details: {service_summary}.",
    ]

    if language == "es":
        contractor_sms_body = (
            f"Nueva cita para {caller_name} el {pretty_time}. "
            f"Dirección del trabajo: {service_address}. Detalles: {service_summary}."
        )
        contractor_email_lines = [
            f"Hola {contractor_name},",
            "",
            f"Está programado para ayudar a {caller_name} el {pretty_time}.",
            f"Resumen del servicio: {service_summary}.",
            f"Dirección del trabajo: {service_address}.",
        ]
        caller_sms_body = (
            f"Hola {caller_name}, su cita con {contractor_name} es el {pretty_time}. "
            f"Nos vemos en {service_address}."
        )
        caller_email_lines = [
            f"Hola {caller_name},",
            "",
            f"Gracias por reservar con {contractor_name}!",
            f"Hora de la cita: {pretty_time}.",
            f"Ubicación: {service_address}.",
            f"Detalles del servicio: {service_summary}.",
        ]

    if contractor_phone:
        body = contractor_sms_body
        if sender_phone:
            body += f" Reply to {sender_phone} if you have questions."
        messages.append(
            NotificationMessage(
                audience="contractor",
                channel="sms",
                recipient=contractor_phone,
                subject=None,
                body=body,
                template="booking_contractor_sms",
                metadata=contractor_context,
                language=contractor_language,
            )
        )

    if contractor_email:
        if language == "es":
            subject = f"Nueva cita confirmada para {pretty_time}"
        else:
            subject = f"New booking confirmed for {pretty_time}"
        body_lines = contractor_email_lines.copy()
        if sender_name and sender_email:
            body_lines.append("")
            if language == "es":
                body_lines.append(f"¿Preguntas? Comuníquese con {sender_name} en {sender_email}.")
            else:
                body_lines.append(f"Questions? Reach {sender_name} at {sender_email}.")
        messages.append(
            NotificationMessage(
                audience="contractor",
                channel="email",
                recipient=contractor_email,
                subject=subject,
                body="\n".join(body_lines),
                template="booking_contractor_email",
                metadata=contractor_context,
                language=contractor_language,
            )
        )

    if caller_phone:
        body = caller_sms_body
        messages.append(
            NotificationMessage(
                audience="caller",
                channel="sms",
                recipient=caller_phone,
                subject=None,
                body=body,
                template="booking_caller_sms",
                metadata=caller_context,
                language=caller_language,
            )
        )

    if caller_email:
        subject = (
            f"Su cita el {pretty_time}"
            if language == "es"
            else f"Your appointment on {pretty_time}"
        )
        body_lines = caller_email_lines.copy()
        if sender_email:
            body_lines.append("")
            if language == "es":
                body_lines.append(f"¿Preguntas? Responda a {sender_email}.")
            else:
                body_lines.append(f"Questions? Reply to {sender_email}.")
        messages.append(
            NotificationMessage(
                audience="caller",
                channel="email",
                recipient=caller_email,
                subject=subject,
                body="\n".join(body_lines),
                template="booking_caller_email",
                metadata=caller_context,
                language=caller_language,
            )
        )

    return messages

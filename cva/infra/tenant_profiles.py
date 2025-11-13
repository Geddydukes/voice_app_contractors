"""Curated tenant templates for onboarding pilots quickly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class TenantProfile:
    """Describes the baseline configuration for a contractor tenant."""

    key: str
    company_name: str
    contact_name: str
    contact_email: str
    contact_phone: str
    services: tuple[str, ...]
    base_location: str
    service_area_radius_km: float
    calendar_provider: str
    calendar_account: str
    notification_sender_email: str
    notification_sender_phone: str
    summary: str
    tone: str
    locale: str
    website: str


BUILT_IN_PROFILES: Dict[str, TenantProfile] = {
    "plumber": TenantProfile(
        key="plumber",
        company_name="Cascade Flow Plumbing",
        contact_name="Ana Martínez",
        contact_email="ana@cascadeflowplumbing.com",
        contact_phone="+12065551234",
        services=(
            "Water heater installations",
            "Emergency repairs",
            "Fixture replacements",
            "Drain cleaning",
        ),
        base_location="500 5th Ave N, Seattle, WA 98109",
        service_area_radius_km=35.0,
        calendar_provider="google",
        calendar_account="dispatch@cascadeflowplumbing.com",
        notification_sender_email="notifications@cascadeflowplumbing.com",
        notification_sender_phone="+12065554321",
        summary=(
            "Family-owned plumbing specialists focused on energy-efficient water heaters "
            "and bilingual service for Seattle-area homeowners."
        ),
        tone="friendly",
        locale="en",
        website="https://cascadeflowplumbing.com",
    ),
}


__all__ = ["TenantProfile", "BUILT_IN_PROFILES"]

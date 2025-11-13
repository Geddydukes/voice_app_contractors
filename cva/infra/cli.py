"""Command line utilities for administering the CVA platform."""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Dict, Iterable

from . import INFRA_ROOT
from .tenant_profiles import BUILT_IN_PROFILES, TenantProfile

PARENT_DIR = INFRA_ROOT.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.append(str(PARENT_DIR))

from shared.leads.store import LeadStore  # type: ignore  # noqa: E402

TENANTS_ROOT = INFRA_ROOT / "tenants"
ENV_TEMPLATE = INFRA_ROOT.parent / ".env.example"


def run_cli(token: str, argv: Iterable[str]) -> int:
    """Dispatch the requested command and return an exit code."""

    argv = list(argv)
    if token == "admin" and argv:
        token = f"admin:{argv.pop(0)}"
    handlers: Dict[str, Callable[[Iterable[str]], int]] = {
        "admin:new-tenant": handle_new_tenant,
        "admin:onboard": handle_onboard,
    }
    handler = handlers.get(token)
    if handler is None:
        print(f"Unknown command: {token}")
        print("Available commands: admin:new-tenant, admin:onboard")
        return 1
    return handler(argv)


def handle_new_tenant(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(prog="cva admin:new-tenant")
    parser.add_argument("tenant_id", help="Unique identifier for the tenant, e.g. cascade-plumbing")
    parser.add_argument(
        "--template",
        default="plumber",
        choices=sorted(BUILT_IN_PROFILES.keys()),
        help="Built-in profile to seed tenant defaults",
    )
    parser.add_argument("--company-name", help="Override the company name for branding")
    parser.add_argument("--contact-name", help="Primary contact name")
    parser.add_argument("--contact-email", help="Primary contact email")
    parser.add_argument("--contact-phone", help="Primary contact phone number")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite any existing tenant directory",
    )
    args = parser.parse_args(list(argv))

    profile = customise_profile(
        BUILT_IN_PROFILES[args.template],
        company_name=args.company_name,
        contact_name=args.contact_name,
        contact_email=args.contact_email,
        contact_phone=args.contact_phone,
    )

    tenant_dir = TENANTS_ROOT / args.tenant_id
    if tenant_dir.exists():
        if not args.force:
            print(f"Tenant directory {tenant_dir} already exists. Use --force to overwrite.")
            return 1
        for existing in tenant_dir.iterdir():
            if existing.is_file():
                existing.unlink()
    tenant_dir.mkdir(parents=True, exist_ok=True)

    env_contents = render_env(profile, tenant_dir, tenant_id=args.tenant_id)
    (tenant_dir / ".env").write_text(env_contents)

    metadata = {
        "tenant_id": args.tenant_id,
        "profile": asdict(profile),
        "notes": "Generated via cva admin:new-tenant",
    }
    (tenant_dir / "tenant.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    (tenant_dir / "README.md").write_text(
        textwrap.dedent(
            f"""
            # {profile.company_name}

            *Tenant ID*: `{args.tenant_id}`
            *Primary Contact*: {profile.contact_name} ({profile.contact_email}, {profile.contact_phone})

            ## Getting Started

            1. Export the environment file:
               ```bash
               export $(grep -v '^#' {tenant_dir}/.env | xargs)
               ```
            2. Start the platform with docker compose.
            3. Run `python -m cva admin:onboard {args.tenant_id}` to finalize dashboard setup.
            """
        ).strip()
        + "\n"
    )

    print(f"Tenant '{args.tenant_id}' created at {tenant_dir}")
    return 0


def handle_onboard(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(prog="cva admin:onboard")
    parser.add_argument("tenant_id", help="Tenant identifier generated via admin:new-tenant")
    parser.add_argument("--owner-name", default="Owner", help="Dashboard owner display name")
    parser.add_argument("--owner-email", required=True, help="Dashboard owner login email")
    parser.add_argument("--owner-password", required=True, help="Temporary dashboard password")
    parser.add_argument(
        "--services",
        help="Comma separated list of offered services",
    )
    parser.add_argument(
        "--base-location",
        help="Business base location for travel calculations",
    )
    parser.add_argument(
        "--radius-km",
        type=float,
        help="Service area radius in kilometers",
    )
    parser.add_argument(
        "--calendar-provider",
        help="Calendar provider identifier (e.g. google, outlook)",
    )
    parser.add_argument(
        "--calendar-account",
        help="Account email used for scheduling",
    )
    parser.add_argument(
        "--seed-demo",
        action="store_true",
        help="Populate lead store with a sample booking and notifications",
    )
    args = parser.parse_args(list(argv))

    tenant_dir = TENANTS_ROOT / args.tenant_id
    if not tenant_dir.exists():
        print(f"Tenant directory {tenant_dir} not found. Run admin:new-tenant first.")
        return 1

    profile = load_profile_from_disk(tenant_dir) or BUILT_IN_PROFILES.get("plumber")

    dashboard_db = tenant_dir / "dashboard.sqlite3"
    lead_store_db = tenant_dir / "lead_store.sqlite3"

    ensure_parent(dashboard_db)
    ensure_parent(lead_store_db)

    store = load_dashboard_store(dashboard_db)
    owner_hash = hash_password(args.owner_password)
    if not store.owner_exists():
        store.create_owner(name=args.owner_name, email=args.owner_email, password_hash=owner_hash)
    else:
        existing = store.get_user_by_email(args.owner_email)
        if existing is None:
            print(
                "Owner already exists with a different email. Use the dashboard UI to manage additional users.",
            )
        else:
            store.update_password(existing.id, owner_hash)

    services = args.services.split(",") if args.services else list(profile.services)
    services_clean = ", ".join(s.strip() for s in services if s.strip())
    base_location = args.base_location or profile.base_location
    radius = args.radius_km or profile.service_area_radius_km
    store.update_settings(
        services=services_clean,
        service_area_radius=radius,
        base_location=base_location,
    )

    provider = args.calendar_provider or profile.calendar_provider
    account = args.calendar_account or profile.calendar_account
    if provider and account:
        store.connect_calendar(provider=provider, account=account)

    lead_store = LeadStore(db_path=str(lead_store_db), tenant_id=args.tenant_id)
    if args.seed_demo:
        seed_demo_data(lead_store, profile)

    (tenant_dir / "onboard.log").write_text(
        textwrap.dedent(
            f"""
            Tenant: {args.tenant_id}
            Owner: {args.owner_name} <{args.owner_email}>
            Services: {services_clean}
            Base Location: {base_location}
            Radius (km): {radius}
            Calendar: {provider or 'not-configured'} / {account or 'n/a'}
            Demo Seeded: {args.seed_demo}
            """
        ).strip()
        + "\n"
    )

    print(f"Tenant '{args.tenant_id}' onboarded. Dashboard credentials ready for {args.owner_email}.")
    return 0


def customise_profile(
    profile: TenantProfile,
    *,
    company_name: str | None = None,
    contact_name: str | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
) -> TenantProfile:
    return TenantProfile(
        key=profile.key,
        company_name=company_name or profile.company_name,
        contact_name=contact_name or profile.contact_name,
        contact_email=contact_email or profile.contact_email,
        contact_phone=contact_phone or profile.contact_phone,
        services=profile.services,
        base_location=profile.base_location,
        service_area_radius_km=profile.service_area_radius_km,
        calendar_provider=profile.calendar_provider,
        calendar_account=profile.calendar_account,
        notification_sender_email=profile.notification_sender_email,
        notification_sender_phone=profile.notification_sender_phone,
        summary=profile.summary,
        tone=profile.tone,
        locale=profile.locale,
        website=profile.website,
    )


def load_profile_from_disk(tenant_dir: Path) -> TenantProfile | None:
    metadata_file = tenant_dir / "tenant.json"
    if not metadata_file.exists():
        return None
    payload = json.loads(metadata_file.read_text())
    profile_data = payload.get("profile") or {}
    services = tuple(profile_data.get("services", ()))
    if not services:
        services = tuple()
    return TenantProfile(
        key=profile_data.get("key", "custom"),
        company_name=profile_data.get("company_name", "Contractor"),
        contact_name=profile_data.get("contact_name", "Owner"),
        contact_email=profile_data.get("contact_email", "owner@example.com"),
        contact_phone=profile_data.get("contact_phone", ""),
        services=services,
        base_location=profile_data.get("base_location", ""),
        service_area_radius_km=float(profile_data.get("service_area_radius_km", 25.0)),
        calendar_provider=profile_data.get("calendar_provider", ""),
        calendar_account=profile_data.get("calendar_account", ""),
        notification_sender_email=profile_data.get("notification_sender_email", "notifications@example.com"),
        notification_sender_phone=profile_data.get("notification_sender_phone", ""),
        summary=profile_data.get("summary", ""),
        tone=profile_data.get("tone", "friendly"),
        locale=profile_data.get("locale", "en"),
        website=profile_data.get("website", ""),
    )


def render_env(profile: TenantProfile, tenant_dir: Path, *, tenant_id: str) -> str:
    if not ENV_TEMPLATE.exists():
        raise SystemExit(f"Environment template not found at {ENV_TEMPLATE}")
    replacements = {
        "TENANT_ID": tenant_id,
        "LEAD_STORE_PATH": str(tenant_dir / "lead_store.sqlite3"),
        "DASHBOARD_DB_PATH": str(tenant_dir / "dashboard.sqlite3"),
        "NOTIFICATION_SENDER": profile.notification_sender_email,
        "NOTIFICATION_SENDER_NAME": profile.company_name,
        "NOTIFICATION_SENDER_PHONE": profile.notification_sender_phone,
        "CALENDAR_RESOURCE_EMAIL": profile.calendar_account,
    }
    rendered_lines = []
    seen_keys = set()
    for line in ENV_TEMPLATE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            rendered_lines.append(line)
            continue
        key, _, _ = line.partition("=")
        key = key.strip()
        seen_keys.add(key)
        value = replacements.get(key)
        if value is None:
            rendered_lines.append(line)
        else:
            rendered_lines.append(f"{key}={value}")
    for key, value in replacements.items():
        if key not in seen_keys:
            rendered_lines.append(f"{key}={value}")
    return "\n".join(rendered_lines) + "\n"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_dashboard_store(db_path: Path):
    dashboard_dir = INFRA_ROOT.parent / "dashboard-service"
    if str(dashboard_dir) not in sys.path:
        sys.path.append(str(dashboard_dir))
    from db import DashboardStore  # type: ignore  # noqa: E402

    return DashboardStore(db_path=db_path)


def hash_password(password: str) -> str:
    dashboard_dir = INFRA_ROOT.parent / "dashboard-service"
    if str(dashboard_dir) not in sys.path:
        sys.path.append(str(dashboard_dir))
    from auth import hash_password as _hash_password  # type: ignore  # noqa: E402

    return _hash_password(password)


def seed_demo_data(store, profile: TenantProfile) -> None:
    from datetime import datetime, timedelta, timezone

    lead = store.create_lead(
        caller_name="Maria Lopez",
        caller_phone="+12065559876",
        caller_email="maria.lopez@example.com",
        transcript=(
            "Hi, I'm looking to schedule a water heater installation next week. I heard you can "
            "handle Spanish-speaking customers."
        ),
        summary="Requested bilingual consultation and installation window for next Tuesday.",
    )
    appointment = datetime.now(tz=timezone.utc) + timedelta(days=3)
    store.record_call(
        lead["id"],
        direction="inbound",
        started_at=appointment - timedelta(minutes=5),
        ended_at=appointment,
        duration_seconds=300,
        transcript=lead["transcript"],
    )
    store.record_message(
        lead["id"],
        direction="outbound",
        channel="sms",
        recipient="+12065559876",
        body=(
            f"Hola Maria, {profile.company_name} confirmó tu instalación el {appointment.date()} a las 10am."
        ),
        template="booking_confirmation",
        status="delivered",
        metadata={"language": "es"},
    )
    store.record_message(
        lead["id"],
        direction="outbound",
        channel="sms",
        recipient=profile.notification_sender_phone,
        body=(
            f"New booking for Maria Lopez on {appointment.date()} at 10am. Check the dashboard for details."
        ),
        template="contractor_alert",
        status="queued",
        metadata={"language": "en"},
    )


__all__ = ["run_cli"]

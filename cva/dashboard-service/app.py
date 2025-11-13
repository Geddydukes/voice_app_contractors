"""FastAPI application that powers the contractor dashboard."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from shared.leads.store import LeadStore
from shared.observability import instrument_app, sanitize_value

from . import auth
from .db import DashboardStore, DashboardStoreError, SettingsRecord, UserRecord

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
TEMPLATES.env.globals["now"] = datetime.utcnow
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Contractor Voice Assistant Dashboard")
logger = instrument_app(app, "dashboard-service")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("DASHBOARD_SECRET_KEY", "dev-dashboard-secret"),
    session_cookie="cva_dashboard",
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_dashboard_store = DashboardStore()
_lead_store = LeadStore()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _current_user(request: Request) -> UserRecord | None:
    user_id = auth.get_current_user_id(request.session)
    if user_id is None:
        return None
    try:
        return _dashboard_store.get_user(user_id)
    except DashboardStoreError:
        auth.clear_current_user(request.session)
        return None


def _require_login(request: Request) -> UserRecord | RedirectResponse:
    user = _current_user(request)
    if user is None:
        auth.add_flash_message(request.session, "Please sign in to continue.", category="warning")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return user


def _require_owner(request: Request) -> UserRecord | RedirectResponse:
    user = _require_login(request)
    if isinstance(user, RedirectResponse):
        return user
    if user.role != "owner":
        auth.add_flash_message(
            request.session,
            "Only the account owner can manage contractor settings.",
            category="error",
        )
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return user


def _template_context(
    request: Request,
    *,
    user: Optional[UserRecord],
    settings: Optional[SettingsRecord] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    context: Dict[str, Any] = {
        "request": request,
        "current_user": user,
        "flashes": auth.pop_flash_messages(request.session),
        "settings": settings,
    }
    if extra:
        context.update(extra)
    return context


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def landing(request: Request):
    if not _dashboard_store.owner_exists():
        return RedirectResponse(url="/onboard", status_code=status.HTTP_303_SEE_OTHER)
    user = _current_user(request)
    target = "/dashboard" if user else "/login"
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


@app.get("/onboard", response_class=HTMLResponse)
def onboard_form(request: Request):
    if _dashboard_store.owner_exists():
        if _current_user(request):
            return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return TEMPLATES.TemplateResponse(
        "onboard.html",
        _template_context(request, user=None, extra={"title": "Create owner account"}),
    )


@app.post("/onboard")
def onboard_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    if _dashboard_store.owner_exists():
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if password != confirm_password:
        auth.add_flash_message(request.session, "Passwords do not match.", category="error")
        return RedirectResponse(url="/onboard", status_code=status.HTTP_303_SEE_OTHER)
    try:
        password_hash = auth.hash_password(password)
        user = _dashboard_store.create_owner(name=name.strip(), email=email.strip(), password_hash=password_hash)
        auth.set_current_user(request.session, user.id)
        auth.add_flash_message(request.session, "Welcome aboard! Let's finish your setup.")
        logger.info("Owner onboarded email=%s", sanitize_value(email))
        return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)
    except (ValueError, DashboardStoreError) as exc:  # pragma: no cover - simple form validation
        auth.add_flash_message(request.session, str(exc), category="error")
        return RedirectResponse(url="/onboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if not _dashboard_store.owner_exists():
        return RedirectResponse(url="/onboard", status_code=status.HTTP_303_SEE_OTHER)
    user = _current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return TEMPLATES.TemplateResponse(
        "login.html",
        _template_context(request, user=None, extra={"title": "Sign in"}),
    )


@app.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    result = _dashboard_store.get_user_with_secret(email.strip())
    if result is None:
        auth.add_flash_message(request.session, "Invalid email or password.", category="error")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    user, stored_hash = result
    if not auth.verify_password(password, stored_hash):
        auth.add_flash_message(request.session, "Invalid email or password.", category="error")
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    auth.set_current_user(request.session, user.id)
    auth.add_flash_message(request.session, f"Welcome back, {user.name.split()[0]}!")
    logger.info("User login email=%s", sanitize_value(email))
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/logout")
def logout(request: Request):
    auth.clear_current_user(request.session)
    auth.add_flash_message(request.session, "You have been signed out.")
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = _require_login(request)
    if isinstance(user, RedirectResponse):
        return user
    settings = _dashboard_store.get_settings()
    leads = list(_lead_store.list_leads())
    total_leads = len(leads)
    scheduled = sum(1 for lead in leads if lead.get("appointment_time"))
    total_calls = sum(len(lead.get("calls", [])) for lead in leads)
    latest_lead = leads[0] if leads else None
    context = {
        "title": "Dashboard",
        "metrics": {
            "total_leads": total_leads,
            "scheduled_leads": scheduled,
            "total_calls": total_calls,
        },
        "latest_lead": latest_lead,
    }
    return TEMPLATES.TemplateResponse(
        "dashboard.html",
        _template_context(request, user=user, settings=settings, extra=context),
    )


@app.get("/leads", response_class=HTMLResponse)
def leads_view(request: Request):
    user = _require_login(request)
    if isinstance(user, RedirectResponse):
        return user
    settings = _dashboard_store.get_settings()
    leads = list(_lead_store.list_leads())
    return TEMPLATES.TemplateResponse(
        "leads.html",
        _template_context(
            request,
            user=user,
            settings=settings,
            extra={"title": "Leads & Calls", "leads": leads},
        ),
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request):
    user = _require_owner(request)
    if isinstance(user, RedirectResponse):
        return user
    settings = _dashboard_store.get_settings()
    staff = list(_dashboard_store.list_staff())
    return TEMPLATES.TemplateResponse(
        "settings.html",
        _template_context(
            request,
            user=user,
            settings=settings,
            extra={"title": "Settings", "staff": staff},
        ),
    )


@app.post("/settings")
def update_settings(
    request: Request,
    services: str = Form(""),
    service_area_radius: float = Form(25.0),
    base_location: str = Form(""),
):
    user = _require_owner(request)
    if isinstance(user, RedirectResponse):
        return user
    try:
        radius = max(0.0, float(service_area_radius))
    except ValueError:
        auth.add_flash_message(request.session, "Service radius must be a number.", category="error")
        return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)
    _dashboard_store.update_settings(
        services=services,
        service_area_radius=radius,
        base_location=base_location,
    )
    auth.add_flash_message(request.session, "Settings updated successfully.")
    logger.info("Settings updated services=%s radius=%.1f", services, radius)
    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/settings/calendar/connect")
def connect_calendar(
    request: Request,
    provider: str = Form(...),
    account: str = Form(...),
):
    user = _require_owner(request)
    if isinstance(user, RedirectResponse):
        return user
    _dashboard_store.connect_calendar(provider=provider, account=account)
    auth.add_flash_message(request.session, "Calendar connected! New bookings will sync automatically.")
    logger.info("Calendar connected provider=%s account=%s", provider, sanitize_value(account))
    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/settings/calendar/disconnect")
def disconnect_calendar(request: Request):
    user = _require_owner(request)
    if isinstance(user, RedirectResponse):
        return user
    _dashboard_store.disconnect_calendar()
    auth.add_flash_message(request.session, "Calendar connection removed.", category="warning")
    logger.info("Calendar disconnected")
    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/settings/staff")
def add_staff(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    user = _require_owner(request)
    if isinstance(user, RedirectResponse):
        return user
    try:
        password_hash = auth.hash_password(password)
        staff = _dashboard_store.create_staff(name=name.strip(), email=email.strip(), password_hash=password_hash)
        auth.add_flash_message(request.session, f"Added {staff.name} as staff.")
        logger.info("Staff added email=%s", sanitize_value(email))
    except (ValueError, DashboardStoreError) as exc:
        auth.add_flash_message(request.session, str(exc), category="error")
    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)

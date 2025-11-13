"""Local persistence helpers for the dashboard service."""

from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DEFAULT_DB_FILENAME = "dashboard.sqlite3"
DEFAULT_DB_PATH = Path(__file__).resolve().parent / DEFAULT_DB_FILENAME


class DashboardStoreError(RuntimeError):
    """Raised when dashboard persistence fails."""


@dataclass(frozen=True)
class UserRecord:
    """Simple projection of a stored dashboard user."""

    id: int
    name: str
    email: str
    role: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SettingsRecord:
    """Represents contractor configuration surfaced in the dashboard."""

    services: str
    service_area_radius: float
    base_location: str
    calendar_provider: str | None
    calendar_account: str | None
    calendar_status: str
    calendar_connected_at: str | None
    updated_at: str


class DashboardStore:
    """Encapsulates dashboard persistence for users and contractor settings."""

    def __init__(self, db_path: str | os.PathLike[str] | None = None) -> None:
        resolved_path = Path(db_path or os.getenv("DASHBOARD_DB_PATH", DEFAULT_DB_PATH))
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            resolved_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._initialize()

    # ------------------------------------------------------------------
    # schema management
    # ------------------------------------------------------------------
    def _initialize(self) -> None:
        with self._conn:  # pragma: no branch - DDL executed atomically
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('owner', 'staff')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    services TEXT NOT NULL,
                    service_area_radius REAL NOT NULL,
                    base_location TEXT NOT NULL,
                    calendar_provider TEXT,
                    calendar_account TEXT,
                    calendar_status TEXT NOT NULL,
                    calendar_connected_at TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

    # ------------------------------------------------------------------
    # user helpers
    # ------------------------------------------------------------------
    def owner_exists(self) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM users WHERE role = 'owner' LIMIT 1"
        ).fetchone()
        return row is not None

    def has_users(self) -> bool:
        row = self._conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        return row is not None

    def create_owner(
        self, *, name: str, email: str, password_hash: str
    ) -> UserRecord:
        with self._lock:
            if self.owner_exists():
                raise DashboardStoreError("Owner already exists")
            now = _timestamp()
            with self._conn:
                cursor = self._conn.execute(
                    """
                    INSERT INTO users (name, email, password_hash, role, created_at, updated_at)
                    VALUES (?, ?, ?, 'owner', ?, ?)
                    """,
                    (name, email.lower(), password_hash, now, now),
                )
                owner_id = cursor.lastrowid
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO settings (
                        id,
                        owner_id,
                        services,
                        service_area_radius,
                        base_location,
                        calendar_provider,
                        calendar_account,
                        calendar_status,
                        calendar_connected_at,
                        updated_at
                    ) VALUES (1, ?, '', 25.0, '', NULL, NULL, 'disconnected', NULL, ?)
                    """,
                    (owner_id, now),
                )
            return self.get_user(owner_id)

    def create_staff(
        self, *, name: str, email: str, password_hash: str
    ) -> UserRecord:
        with self._lock:
            if not self.owner_exists():
                raise DashboardStoreError("Owner must be created before staff")
            now = _timestamp()
            with self._conn:
                cursor = self._conn.execute(
                    """
                    INSERT INTO users (name, email, password_hash, role, created_at, updated_at)
                    VALUES (?, ?, ?, 'staff', ?, ?)
                    """,
                    (name, email.lower(), password_hash, now, now),
                )
                staff_id = cursor.lastrowid
            return self.get_user(staff_id)

    def update_password(self, user_id: int, password_hash: str) -> None:
        with self._lock:
            now = _timestamp()
            with self._conn:
                updated = self._conn.execute(
                    "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                    (password_hash, now, user_id),
                )
            if updated.rowcount == 0:
                raise DashboardStoreError(f"User {user_id} not found")

    def get_user(self, user_id: int) -> UserRecord:
        row = self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise DashboardStoreError(f"User {user_id} not found")
        return _row_to_user(row)

    def get_user_by_email(self, email: str) -> UserRecord | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE lower(email) = ?",
            (email.lower(),),
        ).fetchone()
        return _row_to_user(row) if row else None

    def get_user_with_secret(self, email: str) -> tuple[UserRecord, str] | None:
        row = self._conn.execute(
            "SELECT * FROM users WHERE lower(email) = ?",
            (email.lower(),),
        ).fetchone()
        if row is None:
            return None
        return _row_to_user(row), row["password_hash"]

    def list_staff(self) -> Iterable[UserRecord]:
        rows = self._conn.execute(
            "SELECT * FROM users WHERE role = 'staff' ORDER BY created_at"
        ).fetchall()
        for row in rows:
            yield _row_to_user(row)

    # ------------------------------------------------------------------
    # settings helpers
    # ------------------------------------------------------------------
    def get_settings(self) -> SettingsRecord:
        row = self._conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        if row is None:
            raise DashboardStoreError("Settings not initialized")
        return _row_to_settings(row)

    def update_settings(
        self,
        *,
        services: str,
        service_area_radius: float,
        base_location: str,
    ) -> SettingsRecord:
        with self._lock:
            now = _timestamp()
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE settings
                    SET services = ?,
                        service_area_radius = ?,
                        base_location = ?,
                        updated_at = ?
                    WHERE id = 1
                    """,
                    (services.strip(), service_area_radius, base_location.strip(), now),
                )
        return self.get_settings()

    def connect_calendar(
        self, *, provider: str, account: str
    ) -> SettingsRecord:
        with self._lock:
            now = _timestamp()
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE settings
                    SET calendar_provider = ?,
                        calendar_account = ?,
                        calendar_status = 'connected',
                        calendar_connected_at = ?,
                        updated_at = ?
                    WHERE id = 1
                    """,
                    (provider.strip(), account.strip(), now, now),
                )
        return self.get_settings()

    def disconnect_calendar(self) -> SettingsRecord:
        with self._lock:
            now = _timestamp()
            with self._conn:
                self._conn.execute(
                    """
                    UPDATE settings
                    SET calendar_provider = NULL,
                        calendar_account = NULL,
                        calendar_status = 'disconnected',
                        calendar_connected_at = NULL,
                        updated_at = ?
                    WHERE id = 1
                    """,
                    (now,),
                )
        return self.get_settings()


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _row_to_user(row: sqlite3.Row) -> UserRecord:
    if row is None:
        raise DashboardStoreError("User row expected")
    return UserRecord(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        role=row["role"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_settings(row: sqlite3.Row) -> SettingsRecord:
    if row is None:
        raise DashboardStoreError("Settings row expected")
    return SettingsRecord(
        services=row["services"],
        service_area_radius=float(row["service_area_radius"]),
        base_location=row["base_location"],
        calendar_provider=row["calendar_provider"],
        calendar_account=row["calendar_account"],
        calendar_status=row["calendar_status"],
        calendar_connected_at=row["calendar_connected_at"],
        updated_at=row["updated_at"],
    )


def _timestamp() -> str:
    now = datetime.utcnow().replace(tzinfo=timezone.utc)
    return now.replace(microsecond=0).isoformat().replace("+00:00", "Z")

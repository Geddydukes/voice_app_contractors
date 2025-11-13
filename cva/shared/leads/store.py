"""SQLite-backed lead store used by data and notification services."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from shared.observability.sanitize import sanitize_value

DEFAULT_DB_FILENAME = "lead_store.sqlite3"
DEFAULT_DB_PATH = Path(__file__).resolve().parent / DEFAULT_DB_FILENAME
DEFAULT_TENANT = os.getenv("TENANT_ID", "default")


class LeadStoreError(RuntimeError):
    """Base error raised for lead store operations."""


class LeadNotFoundError(LeadStoreError):
    """Raised when a lead cannot be located."""


@dataclass(frozen=True)
class MessageRecord:
    """Simple dataclass that mirrors a stored notification."""

    id: int
    lead_id: int
    direction: str
    channel: str
    recipient: str
    body: str
    template: str
    status: str | None
    created_at: str
    metadata: Dict[str, Any]


class LeadStore:
    """Manages persistent records for leads, calls, and outbound messages."""

    def __init__(
        self,
        db_path: str | os.PathLike[str] | None = None,
        tenant_id: str | None = None,
    ) -> None:
        resolved_path = Path(db_path or os.getenv("LEAD_STORE_PATH", DEFAULT_DB_PATH))
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            resolved_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        self._tenant_id = (tenant_id or os.getenv("TENANT_ID") or DEFAULT_TENANT).strip() or "default"
        self._initialize()

    # ------------------------------------------------------------------
    # schema management
    # ------------------------------------------------------------------
    def _initialize(self) -> None:
        with self._conn:  # pragma: no branch - DDL executed atomically
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    caller_name TEXT NOT NULL,
                    caller_phone TEXT NOT NULL,
                    caller_email TEXT,
                    transcript TEXT,
                    summary TEXT,
                    appointment_time TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                    call_sid TEXT,
                    direction TEXT,
                    started_at TEXT,
                    ended_at TEXT,
                    duration_seconds INTEGER,
                    transcript TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                    direction TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    body TEXT NOT NULL,
                    template TEXT NOT NULL,
                    status TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

            self._ensure_column("leads", "tenant_id", "TEXT NOT NULL DEFAULT 'default'")

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self._conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition};"
            )

    # ------------------------------------------------------------------
    # creation helpers
    # ------------------------------------------------------------------
    def create_lead(
        self,
        *,
        caller_name: str,
        caller_phone: str,
        caller_email: str | None = None,
        transcript: str | None = None,
        summary: str | None = None,
        appointment_time: datetime | None = None,
    ) -> Dict[str, Any]:
        now = format_iso_timestamp()
        appointment_iso = format_iso_timestamp(appointment_time) if appointment_time else None
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO leads (
                    tenant_id,
                    caller_name,
                    caller_phone,
                    caller_email,
                    transcript,
                    summary,
                    appointment_time,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._tenant_id,
                    caller_name,
                    caller_phone,
                    caller_email,
                    transcript,
                    summary,
                    appointment_iso,
                    now,
                    now,
                ),
            )
            lead_id = cursor.lastrowid
        return self.get_lead(lead_id)

    def record_call(
        self,
        lead_id: int,
        *,
        call_sid: str | None = None,
        direction: str | None = None,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        duration_seconds: int | None = None,
        transcript: str | None = None,
        summary: str | None = None,
    ) -> Dict[str, Any]:
        self._assert_lead_exists(lead_id)
        now = format_iso_timestamp()
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO calls (
                    lead_id,
                    call_sid,
                    direction,
                    started_at,
                    ended_at,
                    duration_seconds,
                    transcript,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead_id,
                    call_sid,
                    direction,
                    format_iso_timestamp(started_at) if started_at else None,
                    format_iso_timestamp(ended_at) if ended_at else None,
                    duration_seconds,
                    transcript,
                    now,
                ),
            )
            if transcript or summary:
                self._conn.execute(
                    """
                    UPDATE leads
                    SET transcript = COALESCE(?, transcript),
                        summary = COALESCE(?, summary),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        transcript,
                        summary,
                        now,
                        lead_id,
                    ),
                )
            call_id = cursor.lastrowid
        return self._row_to_dict(
            self._conn.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
        )

    def record_message(
        self,
        lead_id: int,
        *,
        direction: str,
        channel: str,
        recipient: str,
        body: str,
        template: str,
        status: str | None = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MessageRecord:
        self._assert_lead_exists(lead_id)
        metadata_payload = json.dumps(metadata or {})
        now = format_iso_timestamp()
        with self._conn:
            cursor = self._conn.execute(
                """
                INSERT INTO messages (
                    lead_id,
                    direction,
                    channel,
                    recipient,
                    body,
                    template,
                    status,
                    metadata,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead_id,
                    direction,
                    channel,
                    recipient,
                    body,
                    template,
                    status,
                    metadata_payload,
                    now,
                ),
            )
            self._conn.execute(
                "UPDATE leads SET updated_at = ? WHERE id = ?",
                (now, lead_id),
            )
            message_id = cursor.lastrowid
        row = self._conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
        return MessageRecord(
            id=row["id"],
            lead_id=row["lead_id"],
            direction=row["direction"],
            channel=row["channel"],
            recipient=row["recipient"],
            body=row["body"],
            template=row["template"],
            status=row["status"],
            created_at=row["created_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def update_appointment(self, lead_id: int, appointment_time: datetime) -> None:
        self._assert_lead_exists(lead_id)
        now = format_iso_timestamp()
        with self._conn:
            self._conn.execute(
                "UPDATE leads SET appointment_time = ?, updated_at = ? WHERE id = ?",
                (
                    format_iso_timestamp(appointment_time),
                    now,
                    lead_id,
                ),
            )

    # ------------------------------------------------------------------
    # retrieval helpers
    # ------------------------------------------------------------------
    def get_lead(self, lead_id: int) -> Dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM leads WHERE id = ? AND tenant_id = ?",
            (lead_id, self._tenant_id),
        ).fetchone()
        if row is None:
            raise LeadNotFoundError(f"Lead {lead_id} not found")
        lead = self._row_to_dict(row)
        lead["calls"] = [
            self._row_to_dict(call)
            for call in self._conn.execute(
                "SELECT * FROM calls WHERE lead_id = ? ORDER BY created_at", (lead_id,)
            ).fetchall()
        ]
        lead["messages"] = [
            self._normalize_message_row(message)
            for message in self._conn.execute(
                "SELECT * FROM messages WHERE lead_id = ? ORDER BY created_at", (lead_id,)
            ).fetchall()
        ]
        return lead

    def list_leads(self) -> Iterable[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM leads WHERE tenant_id = ? ORDER BY created_at DESC",
            (self._tenant_id,),
        ).fetchall()
        for row in rows:
            yield self.get_lead(row["id"])

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _assert_lead_exists(self, lead_id: int) -> None:
        row = self._conn.execute(
            "SELECT 1 FROM leads WHERE id = ? AND tenant_id = ?",
            (lead_id, self._tenant_id),
        ).fetchone()
        if row is None:
            raise LeadNotFoundError(f"Lead {lead_id} not found")

    def _row_to_dict(self, row: sqlite3.Row | None) -> Dict[str, Any]:
        if row is None:
            raise LeadStoreError("Row expected but none returned")
        data = dict(row)
        metadata = data.get("metadata")
        if isinstance(metadata, str):
            data["metadata"] = json.loads(metadata) if metadata else {}
        data["caller_phone"] = sanitize_value(data.get("caller_phone"))
        data["caller_email"] = sanitize_value(data.get("caller_email"))
        return data

    def _normalize_message_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        payload = dict(row)
        payload["metadata"] = json.loads(payload["metadata"]) if payload["metadata"] else {}
        payload["recipient"] = sanitize_value(payload.get("recipient"))
        return payload


def format_iso_timestamp(value: datetime | None = None) -> str:
    """Return an ISO 8601 timestamp with UTC ``Z`` suffix."""

    if value is None:
        value = datetime.utcnow().replace(tzinfo=timezone.utc)
    elif value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")

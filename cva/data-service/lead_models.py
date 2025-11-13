"""Pydantic schemas for lead storage endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    if value.endswith("Z"):
        value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


class LeadCallRecord(BaseModel):
    id: int
    call_sid: str | None = None
    direction: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    transcript: str | None = None
    created_at: datetime

    @field_validator("started_at", "ended_at", "created_at", mode="before")
    @classmethod
    def _parse_ts(cls, value: Any):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return _parse_timestamp(value)


class LeadMessageRecord(BaseModel):
    id: int
    direction: str
    channel: str
    recipient: str
    body: str
    template: str
    status: str | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _parse_created_at(cls, value: Any):
        if isinstance(value, datetime):
            return value
        return _parse_timestamp(value)


class LeadRecord(BaseModel):
    id: int
    caller_name: str
    caller_phone: str
    caller_email: EmailStr | None = None
    transcript: str | None = None
    summary: str | None = None
    appointment_time: datetime | None = None
    created_at: datetime
    updated_at: datetime
    calls: List[LeadCallRecord] = Field(default_factory=list)
    messages: List[LeadMessageRecord] = Field(default_factory=list)

    @field_validator("created_at", "updated_at", "appointment_time", mode="before")
    @classmethod
    def _parse_datetime(cls, value: Any):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return _parse_timestamp(value)


class LeadCreateRequest(BaseModel):
    caller_name: str
    caller_phone: str
    caller_email: EmailStr | None = None
    transcript: str
    summary: str
    appointment_time: datetime | None = None


class LeadCreateResponse(BaseModel):
    lead: LeadRecord


class CallLogRequest(BaseModel):
    call_sid: str | None = None
    direction: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    transcript: str | None = None
    summary: str | None = None


class CallLogResponse(BaseModel):
    call: LeadCallRecord


class MessageLogRequest(BaseModel):
    direction: str = Field(default="outbound")
    channel: str
    recipient: str
    body: str
    template: str
    status: str | None = None
    metadata: Optional[Dict[str, Any]] = None


class MessageLogResponse(BaseModel):
    message: LeadMessageRecord


class LeadListResponse(BaseModel):
    leads: List[LeadRecord]

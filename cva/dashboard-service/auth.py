"""Authentication utilities for the dashboard."""

from __future__ import annotations

import hashlib
import os
from typing import List, MutableMapping

SESSION_USER_KEY = "dashboard_user_id"
FLASH_SESSION_KEY = "dashboard_flash_messages"


def hash_password(password: str) -> str:
    """Return a salted SHA-256 hash for the provided password."""

    if not password:
        raise ValueError("Password cannot be empty")
    salt = os.urandom(16).hex()
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Validate that the password matches the stored salted hash."""

    try:
        salt, digest = stored_hash.split("$", 1)
    except ValueError:
        return False
    candidate = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return candidate == digest


def set_current_user(session: MutableMapping[str, object], user_id: int) -> None:
    session[SESSION_USER_KEY] = user_id


def get_current_user_id(session: MutableMapping[str, object]) -> int | None:
    user_id = session.get(SESSION_USER_KEY)
    if isinstance(user_id, int):
        return user_id
    if isinstance(user_id, str) and user_id.isdigit():
        return int(user_id)
    return None


def clear_current_user(session: MutableMapping[str, object]) -> None:
    session.pop(SESSION_USER_KEY, None)


def add_flash_message(
    session: MutableMapping[str, object], message: str, *, category: str = "info"
) -> None:
    payload = {"message": message, "category": category}
    existing = session.get(FLASH_SESSION_KEY)
    if isinstance(existing, list):
        existing.append(payload)
        session[FLASH_SESSION_KEY] = existing
    else:
        session[FLASH_SESSION_KEY] = [payload]


def pop_flash_messages(session: MutableMapping[str, object]) -> List[dict[str, str]]:
    messages = session.pop(FLASH_SESSION_KEY, [])
    return messages if isinstance(messages, list) else []

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from .config import CalendarConfig
from .models import OAuthToken


class OAuthClient:
    """Lightweight OAuth simulation that mimics refreshing access tokens."""

    def __init__(self, config: CalendarConfig) -> None:
        self._config = config
        self._token: OAuthToken | None = None

    def current_token(self) -> OAuthToken:
        if self._token is None or self._token.is_expired():
            self._token = self._refresh_token()
        return self._token

    def _refresh_token(self) -> OAuthToken:
        access_token = secrets.token_hex(16)
        expires_at = datetime.utcnow() + timedelta(hours=1)
        return OAuthToken(access_token=access_token, expires_at=expires_at)

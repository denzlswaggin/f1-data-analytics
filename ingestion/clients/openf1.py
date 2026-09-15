"""Minimal client for the OpenF1 API (https://openf1.org).

Used for timestamped timing-state evidence (position changes and intervals) and
team-radio clips. Kept tiny: a polite rate limit and 404 -> empty (OpenF1 returns
``{"detail": "No results found."}`` with a 404 when an endpoint has no rows).
"""

from __future__ import annotations

import time
from typing import Any

import requests

from ingestion.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://api.openf1.org/v1"


class OpenF1AuthenticationError(RuntimeError):
    """OpenF1 requires credentials that were absent or rejected."""


class OpenF1Client:
    """Thin, rate-limited reader for the OpenF1 endpoints we need."""

    def __init__(
        self,
        base_url: str = _BASE_URL,
        min_interval_s: float = 0.35,
        *,
        username: str = "",
        password: str = "",
        access_token: str = "",
    ) -> None:
        self.base_url = base_url
        self._min_interval = min_interval_s
        self._last = 0.0
        self._username = username
        self._password = password
        self._session = requests.Session()
        if access_token:
            self._session.headers.update({"Authorization": f"Bearer {access_token}"})

    @property
    def token_url(self) -> str:
        """OAuth endpoint adjacent to the versioned REST base URL."""
        api_root = self.base_url.removesuffix("/v1")
        return f"{api_root}/token"

    def _authenticate(self) -> None:
        if not self._username or not self._password:
            raise OpenF1AuthenticationError(
                "OpenF1 restricted access during a live session. Configure "
                "F1_OPENF1_USERNAME and F1_OPENF1_PASSWORD (or a short-lived "
                "F1_OPENF1_ACCESS_TOKEN) to refresh team radio now."
            )
        response = self._session.post(
            self.token_url,
            data={"username": self._username, "password": self._password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        if response.status_code != 200:
            raise OpenF1AuthenticationError(
                f"OpenF1 authentication failed with HTTP {response.status_code}"
            )
        payload = response.json()
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise OpenF1AuthenticationError("OpenF1 authentication returned no access token")
        self._session.headers.update({"Authorization": f"Bearer {token}"})

    def _get(self, path: str, **params: Any) -> list[dict[str, Any]]:
        elapsed = time.monotonic() - self._last
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        resp = self._session.get(f"{self.base_url}/{path}", params=params, timeout=30)
        self._last = time.monotonic()
        if resp.status_code == 401:
            self._authenticate()
            resp = self._session.get(f"{self.base_url}/{path}", params=params, timeout=30)
            self._last = time.monotonic()
            if resp.status_code == 401:
                raise OpenF1AuthenticationError(
                    "OpenF1 rejected the configured credential with HTTP 401"
                )
        if resp.status_code == 404:  # OpenF1's "no results" for an empty query
            return []
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    def race_sessions(self, year: int) -> list[dict[str, Any]]:
        """All 'Race' sessions for a season (each has session_key + date_start)."""
        return self._get("sessions", year=year, session_name="Race")

    def team_radio(self, session_key: int) -> list[dict[str, Any]]:
        """Team-radio clips for a session: date, driver_number, recording_url."""
        return self._get("team_radio", session_key=session_key)

    def drivers(self, session_key: int) -> list[dict[str, Any]]:
        """Declared drivers and stable number/code mapping for one session."""
        return self._get("drivers", session_key=session_key)

    def positions(self, session_key: int) -> list[dict[str, Any]]:
        """Timestamped full-session driver position state changes."""
        return self._get("position", session_key=session_key)

    def intervals(self, session_key: int) -> list[dict[str, Any]]:
        """Timestamped gaps to the leader and the car ahead."""
        return self._get("intervals", session_key=session_key)

    def laps(self, session_key: int) -> list[dict[str, Any]]:
        """OpenF1 lap boundaries used to audit clock alignment."""
        return self._get("laps", session_key=session_key)

    def race_control(self, session_key: int) -> list[dict[str, Any]]:
        """Secondary timestamped race-control feed for boundary reconciliation."""
        return self._get("race_control", session_key=session_key)

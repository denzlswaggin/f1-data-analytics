"""Minimal client for the OpenF1 API (https://openf1.org).

Used only for **team-radio** clips (timestamped MP3 recordings per driver), which
neither Jolpica nor the F1 archive expose for the current season. Kept tiny: a
polite rate limit and 404 -> empty (OpenF1 returns ``{"detail": "No results
found."}`` with a 404 when a session has no clips).
"""

from __future__ import annotations

import time
from typing import Any

import requests

from ingestion.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://api.openf1.org/v1"


class OpenF1Client:
    """Thin, rate-limited reader for the OpenF1 endpoints we need."""

    def __init__(self, base_url: str = _BASE_URL, min_interval_s: float = 0.35) -> None:
        self.base_url = base_url
        self._min_interval = min_interval_s
        self._last = 0.0
        self._session = requests.Session()

    def _get(self, path: str, **params: Any) -> list[dict[str, Any]]:
        elapsed = time.monotonic() - self._last
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        resp = self._session.get(f"{self.base_url}/{path}", params=params, timeout=30)
        self._last = time.monotonic()
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

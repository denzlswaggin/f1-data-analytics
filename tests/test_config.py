"""Runtime configuration tests."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from ingestion.config import Settings


def test_current_season_defaults_to_calendar_year(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Pydantic reads the environment when Settings is created; keep the default
    # deterministic by ensuring a developer override is absent.
    monkeypatch.delenv("F1_CURRENT_SEASON", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.current_season == dt.date.today().year


def test_current_season_accepts_environment_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("F1_CURRENT_SEASON", "2030")
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.current_season == 2030


def test_required_health_resources_are_trimmed_and_deduplicated() -> None:
    settings = Settings(health_required_resources=" laps,telemetry, laps, ")

    assert settings.required_health_resources == ("laps", "telemetry")

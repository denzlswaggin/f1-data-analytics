"""Runtime configuration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from ingestion.config import Settings


def test_current_season_defaults_to_last_supported_season(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Pydantic reads the environment when Settings is created; keep the default
    # deterministic by ensuring a developer override is absent.
    monkeypatch.delenv("F1_CURRENT_SEASON", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.current_season == 2026


def test_current_season_accepts_environment_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("F1_CURRENT_SEASON", "2025")
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.current_season == 2025


@pytest.mark.parametrize("season", [2023, 2027])
def test_current_season_rejects_outside_context(
    season: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        Settings(current_season=season)


def test_required_health_resources_are_trimmed_and_deduplicated() -> None:
    settings = Settings(health_required_resources=" laps,telemetry, laps, ")

    assert settings.required_health_resources == ("laps", "telemetry")


def test_postgres_requires_an_explicit_password(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("F1_PG_PASSWORD", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings(warehouse="postgres")

    with pytest.raises(ValueError, match="F1_PG_PASSWORD must be set"):
        _ = settings.pg_dsn

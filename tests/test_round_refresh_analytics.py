"""Tests for the round refresh's Python-built analytics fan-out."""

from pathlib import Path

import pandas as pd
import pytest
from analytics.race_control_impact import RaceControlImpactResult
from analytics.traffic import TrafficPaceResult
from analytics.tyre_warmup import TyreWarmupResult
from ingestion.config import Settings
from orchestration import round_refresh
from orchestration.constants import PACE_PROFILE_FROM_SEASON


def test_round_refresh_rebuilds_every_dashboard_analytics_mart(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, object]] = []

    def ratings(*, settings: Settings) -> pd.DataFrame:
        calls.append(("ratings", settings))
        return pd.DataFrame(index=range(2))

    def ratings_v2(*, settings: Settings) -> pd.DataFrame:
        calls.append(("ratings_v2", settings))
        return pd.DataFrame(index=range(3))

    def pace_profile(*, from_season: int, settings: Settings) -> pd.DataFrame:
        calls.append(("pace_profile", (from_season, settings)))
        return pd.DataFrame(index=range(4))

    def replay(season: int, rnd: int, *, settings: Settings) -> pd.DataFrame:
        calls.append(("replay", (season, rnd, settings)))
        return pd.DataFrame(index=range(5))

    def overtakes(season: int, rnd: int, *, settings: Settings) -> pd.DataFrame:
        calls.append(("overtakes", (season, rnd, settings)))
        return pd.DataFrame(index=range(6))

    def pit_windows(season: int, rnd: int, *, settings: Settings) -> pd.DataFrame:
        calls.append(("pit_windows", (season, rnd, settings)))
        return pd.DataFrame(index=range(9))

    def race_control(season: int, rnd: int, *, settings: Settings) -> RaceControlImpactResult:
        calls.append(("race_control", (season, rnd, settings)))
        return RaceControlImpactResult(
            events=pd.DataFrame(index=range(10)),
            evidence=pd.DataFrame(index=range(11)),
        )

    def traffic(season: int, rnd: int, *, settings: Settings) -> TrafficPaceResult:
        calls.append(("traffic", (season, rnd, settings)))
        return TrafficPaceResult(
            evidence=pd.DataFrame(index=range(8)),
            summary=pd.DataFrame(index=range(7)),
        )

    def tyre_warmup(season: int, rnd: int, *, settings: Settings) -> TyreWarmupResult:
        calls.append(("tyre_warmup", (season, rnd, settings)))
        return TyreWarmupResult(
            summary=pd.DataFrame(index=range(12)),
            laps=pd.DataFrame(index=range(13)),
        )

    monkeypatch.setattr(round_refresh, "build_driver_ratings", ratings)
    monkeypatch.setattr(round_refresh, "build_driver_ratings_v2", ratings_v2)
    monkeypatch.setattr(round_refresh, "build_driver_pace_profile", pace_profile)
    monkeypatch.setattr(round_refresh, "build_race_replay_incremental", replay)
    monkeypatch.setattr(round_refresh, "build_traffic_adjusted_pace_incremental", traffic)
    monkeypatch.setattr(round_refresh, "build_tyre_warmup_incremental", tyre_warmup)
    monkeypatch.setattr(round_refresh, "build_pit_window_effectiveness_incremental", pit_windows)
    monkeypatch.setattr(round_refresh, "build_race_control_impact_incremental", race_control)
    monkeypatch.setattr(round_refresh, "build_race_overtakes_incremental", overtakes)
    settings = Settings(duckdb_path=tmp_path / "round.duckdb")

    summary = round_refresh._build_round_analytics(2026, 12, settings)

    assert summary == {
        "ratings": 2,
        "dynamic_ratings": 3,
        "pace_profiles": 4,
        "replay_rows": 5,
        "traffic_pace_drivers": 7,
        "tyre_warmup_stints": 12,
        "tyre_warmup_laps": 13,
        "pit_window_matchups": 9,
        "race_control_events": 10,
        "race_control_observations": 11,
        "overtakes": 6,
    }
    assert [name for name, _ in calls] == [
        "ratings",
        "ratings_v2",
        "pace_profile",
        "replay",
        "traffic",
        "tyre_warmup",
        "pit_windows",
        "race_control",
        "overtakes",
    ]
    assert calls[2][1] == (PACE_PROFILE_FROM_SEASON, settings)
    assert calls[3][1] == (2026, 12, settings)
    assert calls[4][1] == (2026, 12, settings)
    assert calls[5][1] == (2026, 12, settings)
    assert calls[6][1] == (2026, 12, settings)
    assert calls[7][1] == (2026, 12, settings)
    assert calls[8][1] == (2026, 12, settings)

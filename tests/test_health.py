"""Tests for audit-backed operational health checks."""

import datetime as dt
from pathlib import Path

import pandas as pd
from ingestion.config import Settings
from ingestion.health import evaluate_pipeline_health
from ingestion.loaders.warehouse import load_dataframe


def _core_frame(season: int) -> pd.DataFrame:
    return pd.DataFrame({"season": [season], "round": [1], "value": ["ok"]})


def test_pipeline_health_passes_for_recent_core_loads(tmp_path: Path) -> None:
    settings = Settings(duckdb_path=tmp_path / "health.duckdb", current_season=2024)
    for resource in ("races", "results", "qualifying"):
        load_dataframe(_core_frame(2024), resource, 2024, settings)

    checks = evaluate_pipeline_health(
        settings,
        now=dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        max_age_hours=2,
    )

    assert checks
    assert all(check.passed for check in checks)


def test_pipeline_health_reports_missing_resource_and_stale_load(tmp_path: Path) -> None:
    settings = Settings(duckdb_path=tmp_path / "health.duckdb", current_season=2024)
    load_dataframe(_core_frame(2024), "races", 2024, settings)

    checks = evaluate_pipeline_health(
        settings,
        now=dt.datetime.now(dt.UTC) + dt.timedelta(days=2),
        max_age_hours=24,
    )
    by_name = {check.name: check for check in checks}

    assert not by_name["core_resource_results"].passed
    assert not by_name["core_resource_qualifying"].passed
    assert not by_name["latest_load_age"].passed


def test_pipeline_health_handles_missing_audit_table(tmp_path: Path) -> None:
    settings = Settings(duckdb_path=tmp_path / "missing.duckdb", current_season=2024)

    checks = evaluate_pipeline_health(settings)

    assert checks == [checks[0]]
    assert checks[0].name == "audit_table"
    assert not checks[0].passed

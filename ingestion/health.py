"""Operational health checks backed by the durable ingestion audit table."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

import duckdb
import pandas as pd
from sqlalchemy import create_engine

from ingestion.config import Settings, get_settings
from ingestion.loaders.warehouse import read_query

CORE_RESOURCES = ("races", "results", "qualifying")


@dataclass(frozen=True)
class HealthCheck:
    """One machine-readable pipeline health assertion."""

    name: str
    passed: bool
    detail: str


def evaluate_pipeline_health(
    settings: Settings | None = None,
    *,
    season: int | None = None,
    max_age_hours: float = 192.0,
    now: dt.datetime | None = None,
    required_resources: Sequence[str] | None = None,
) -> list[HealthCheck]:
    """Check required coverage, non-empty loads, and successful load age.

    Races, results, and qualifying are always required. Heavy sources are
    opt-in because not every deployment installs the FastF1 telemetry extra.
    """
    settings = settings or get_settings()
    season = season or settings.current_season
    now = now or dt.datetime.now(dt.UTC)
    optional = required_resources
    if optional is None:
        optional = settings.required_health_resources
    expected_resources = tuple(dict.fromkeys((*CORE_RESOURCES, *optional)))
    try:
        audits = read_query(
            "select resource, season, round, session, loaded_at, row_count "
            f"from raw.ingestion_partitions where season = {int(season)}",
            settings,
        )
    except Exception as exc:
        return [HealthCheck("audit_table", False, f"unavailable: {exc}")]

    checks = [
        HealthCheck(
            "audit_table",
            not audits.empty,
            f"{len(audits)} audited partitions for {season}",
        )
    ]
    for resource in expected_resources:
        rows = audits[audits["resource"] == resource]
        prefix = "core_resource" if resource in CORE_RESOURCES else "required_resource"
        has_valid_rows = not rows.empty and bool((rows["row_count"] > 0).all())
        checks.append(
            HealthCheck(
                f"{prefix}_{resource}",
                has_valid_rows,
                f"{len(rows)} non-empty audited partition(s)",
            )
        )
        resource_loaded_at = pd.to_datetime(rows["loaded_at"], utc=True, errors="coerce").max()
        resource_age_hours = (
            float("inf")
            if pd.isna(resource_loaded_at)
            else (now - resource_loaded_at.to_pydatetime()).total_seconds() / 3600
        )
        checks.append(
            HealthCheck(
                f"{prefix}_{resource}_load_age",
                resource_age_hours <= max_age_hours,
                f"latest {resource} load is {resource_age_hours:.1f}h old "
                f"(limit {max_age_hours:.1f}h)",
            )
        )

    if audits.empty:
        checks.append(HealthCheck("latest_load_age", False, "no successful loads recorded"))
        return checks

    loaded_at = pd.to_datetime(audits["loaded_at"], utc=True, errors="coerce").max()
    age_hours = (
        float("inf")
        if pd.isna(loaded_at)
        else (now - loaded_at.to_pydatetime()).total_seconds() / 3600
    )
    checks.append(
        HealthCheck(
            "latest_load_age",
            age_hours <= max_age_hours,
            f"latest audited load is {age_hours:.1f}h old (limit {max_age_hours:.1f}h)",
        )
    )
    return checks


def record_pipeline_health(
    checks: Sequence[HealthCheck],
    settings: Settings | None = None,
    *,
    season: int | None = None,
    checked_at: dt.datetime | None = None,
) -> int:
    """Append health results to ``ops.pipeline_health_history`` for trend analysis."""
    settings = settings or get_settings()
    checked_at = checked_at or dt.datetime.now(dt.UTC)
    season = season or settings.current_season
    frame = pd.DataFrame(
        [
            {
                "checked_at": checked_at,
                "season": season,
                "check_name": check.name,
                "passed": check.passed,
                "detail": check.detail,
            }
            for check in checks
        ]
    )
    if frame.empty:
        return 0

    if settings.warehouse == "duckdb":
        settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(settings.duckdb_path)) as connection:
            connection.register("health_results", frame)
            connection.execute("CREATE SCHEMA IF NOT EXISTS ops")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS ops.pipeline_health_history AS "
                "SELECT * FROM health_results WHERE 1 = 0"
            )
            connection.execute(
                "INSERT INTO ops.pipeline_health_history BY NAME SELECT * FROM health_results"
            )
            connection.unregister("health_results")
    else:
        engine = create_engine(settings.pg_dsn)
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS ops")
                frame.to_sql(
                    "pipeline_health_history",
                    connection,
                    schema="ops",
                    if_exists="append",
                    index=False,
                )
        finally:
            engine.dispose()
    return len(frame)

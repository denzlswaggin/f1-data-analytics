"""Operational health checks backed by the durable ingestion audit table."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

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
) -> list[HealthCheck]:
    """Check core coverage, non-empty loads, and latest successful load age."""
    settings = settings or get_settings()
    season = season or settings.current_season
    now = now or dt.datetime.now(dt.UTC)
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
    for resource in CORE_RESOURCES:
        rows = audits[audits["resource"] == resource]
        checks.append(
            HealthCheck(
                f"core_resource_{resource}",
                not rows.empty and bool((rows["row_count"] > 0).all()),
                f"{len(rows)} non-empty audited partition(s)",
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

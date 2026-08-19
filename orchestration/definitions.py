"""Dagster Definitions: assets, the refresh job, a schedule, and the dbt resource.

Run locally from the repo root:

    dagster dev -m orchestration.definitions
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from dagster import (
    AssetKey,
    AssetSelection,
    Definitions,
    RunFailureSensorContext,
    ScheduleDefinition,
    define_asset_job,
    run_failure_sensor,
)
from dagster_dbt import DbtCliResource
from ingestion.logging import get_logger

from orchestration.assets import (
    dbt_models,
    dbt_project,
    driver_ratings,
    driver_ratings_are_sane,
    race_replay,
    raw_ergast_laps,
    raw_laps,
    raw_pitstops,
    raw_positions,
    raw_qualifying,
    raw_race_control,
    raw_races,
    raw_races_current_season_present,
    raw_results,
    raw_team_radio,
    raw_telemetry,
    raw_weather,
)

log = get_logger(__name__)


def _dbt_executable() -> str:
    """Locate the dbt CLI: PATH first, else the venv Scripts dir next to python."""
    found = shutil.which("dbt")
    if found:
        return found
    candidate = Path(sys.executable).parent / ("dbt.exe" if sys.platform == "win32" else "dbt")
    return str(candidate) if candidate.exists() else "dbt"


all_assets = [
    raw_races,
    raw_results,
    raw_qualifying,
    raw_laps,
    raw_pitstops,
    raw_ergast_laps,
    raw_weather,
    raw_telemetry,
    raw_positions,
    raw_race_control,
    raw_team_radio,
    dbt_models,
    driver_ratings,
    race_replay,
]

# Full end-to-end refresh: ingest -> dbt -> ratings + replay. The heavy / cache-
# dependent FastF1 + OpenF1 ingests — raw.telemetry, raw.positions, raw.race_control
# and raw.team_radio — are excluded from the weekly job; materialise them on demand.
# Downstream dbt/analytics still rebuild each run from whatever has been ingested.
refresh_job = define_asset_job(
    name="refresh_pipeline",
    selection=AssetSelection.all()
    - AssetSelection.assets(
        AssetKey(["raw", "telemetry"]),
        AssetKey(["raw", "positions"]),
        AssetKey(["raw", "race_control"]),
        AssetKey(["raw", "team_radio"]),
    ),
)

# Race weekends finish Sunday; refresh Monday morning.
race_weekend_schedule = ScheduleDefinition(
    name="race_weekend_refresh",
    job=refresh_job,
    cron_schedule="0 6 * * 1",
)


# Structured alert on any run failure. Logs via structlog (JSON in prod); this is
# the single place to wire a Slack / PagerDuty webhook when one is available.
@run_failure_sensor(description="Emit a structured alert when any run fails.")
def alert_on_run_failure(context: RunFailureSensorContext) -> None:
    log.error(
        "dagster.run_failed",
        run_id=context.dagster_run.run_id,
        job_name=context.dagster_run.job_name,
        error=context.failure_event.message,
    )


defs = Definitions(
    assets=all_assets,
    asset_checks=[raw_races_current_season_present, driver_ratings_are_sane],
    jobs=[refresh_job],
    schedules=[race_weekend_schedule],
    sensors=[alert_on_run_failure],
    resources={"dbt": DbtCliResource(project_dir=dbt_project, dbt_executable=_dbt_executable())},
)

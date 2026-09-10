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
    define_asset_job,
    run_failure_sensor,
)
from dagster_dbt import DbtCliResource
from ingestion.alerts import AlertDeliveryError, send_webhook_alert
from ingestion.config import get_settings
from ingestion.logging import get_logger

from orchestration.assets import (
    DBT_PROJECT_DIR,
    SEASON_PARTITIONS,
    dbt_models,
    dbt_project,
    driver_pace_profile,
    driver_pace_profile_is_sane,
    driver_ratings,
    driver_ratings_are_sane,
    driver_ratings_v2,
    driver_ratings_v2_are_sane,
    driver_ratings_v3,
    driver_ratings_v3_are_sane,
    race_overtakes,
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
    raw_results_current_load_is_fresh,
    raw_team_radio,
    raw_telemetry,
    raw_weather,
    traffic_adjusted_pace,
)
from orchestration.round_refresh import (
    latest_round_schedule,
    round_refresh_job,
)

log = get_logger(__name__)
settings = get_settings()


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
    driver_ratings_v2,
    driver_ratings_v3,
    driver_pace_profile,
    race_replay,
    traffic_adjusted_pace,
    race_overtakes,
]

# Broad season refresh: ingest -> dbt -> ratings + replay, partitioned by
# season. Heavy cache-dependent sources remain excluded here; the scheduled
# round_refresh_job handles those one completed race at a time. This job stays
# available for explicit season rebuilds and historical maintenance.
refresh_job = define_asset_job(
    name="refresh_pipeline",
    selection=AssetSelection.all()
    - AssetSelection.assets(
        AssetKey(["raw", "telemetry"]),
        AssetKey(["raw", "positions"]),
        AssetKey(["raw", "race_control"]),
        AssetKey(["raw", "team_radio"]),
    ),
    partitions_def=SEASON_PARTITIONS,
)

# Backfill entry point: (re)materialise the raw ingestion for any season (or a
# range) from the Dagster UI / `dagster job backfill`. Partitioned by season.
backfill_ingest_job = define_asset_job(
    name="backfill_ingest",
    selection=AssetSelection.groups("ingest"),
    partitions_def=SEASON_PARTITIONS,
)


# Structured alert on any run failure. Delivery uses a configurable generic
# webhook so Slack/PagerDuty relays and self-hosted incident systems work without
# hard-coding a provider SDK or credential.
@run_failure_sensor(description="Log and deliver a webhook alert when any run fails.")
def alert_on_run_failure(context: RunFailureSensorContext) -> None:
    log.error(
        "dagster.run_failed",
        run_id=context.dagster_run.run_id,
        job_name=context.dagster_run.job_name,
        error=context.failure_event.message,
    )
    try:
        delivered = send_webhook_alert(
            "dagster.run_failed",
            context.failure_event.message or "Dagster run failed without an error message",
            attributes={
                "run_id": context.dagster_run.run_id,
                "job_name": context.dagster_run.job_name,
            },
            settings=settings,
        )
        if not delivered:
            log.warning("dagster.alert_webhook_not_configured")
    except AlertDeliveryError as exc:
        # The original failed run remains the incident of record. Alert transport
        # errors are logged without recursively failing another Dagster run.
        log.error("dagster.alert_delivery_failed", error=str(exc))


defs = Definitions(
    assets=all_assets,
    asset_checks=[
        raw_races_current_season_present,
        raw_results_current_load_is_fresh,
        driver_ratings_are_sane,
        driver_ratings_v2_are_sane,
        driver_ratings_v3_are_sane,
        driver_pace_profile_is_sane,
    ],
    jobs=[refresh_job, backfill_ingest_job, round_refresh_job],
    schedules=[latest_round_schedule],
    sensors=[alert_on_run_failure],
    resources={
        "dbt": DbtCliResource(
            project_dir=dbt_project,
            profiles_dir=DBT_PROJECT_DIR,
            target="prod" if settings.warehouse == "postgres" else "dev",
            dbt_executable=_dbt_executable(),
        )
    },
)

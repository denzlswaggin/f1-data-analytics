"""Dagster Definitions: assets, the refresh job, a schedule, and the dbt resource.

Run locally from the repo root:

    dagster dev -m orchestration.definitions
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from dagster import Definitions, ScheduleDefinition, define_asset_job
from dagster_dbt import DbtCliResource

from orchestration.assets import (
    dbt_models,
    dbt_project,
    driver_ratings,
    raw_ergast_laps,
    raw_laps,
    raw_pitstops,
    raw_qualifying,
    raw_races,
    raw_results,
)


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
    dbt_models,
    driver_ratings,
]

# Full end-to-end refresh: ingest -> dbt -> ratings.
refresh_job = define_asset_job(name="refresh_pipeline", selection="*")

# Race weekends finish Sunday; refresh Monday morning.
race_weekend_schedule = ScheduleDefinition(
    name="race_weekend_refresh",
    job=refresh_job,
    cron_schedule="0 6 * * 1",
)

defs = Definitions(
    assets=all_assets,
    jobs=[refresh_job],
    schedules=[race_weekend_schedule],
    resources={"dbt": DbtCliResource(project_dir=dbt_project, dbt_executable=_dbt_executable())},
)

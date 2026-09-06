"""Shared orchestration settings that do not require loading the dbt manifest."""

from ingestion.config import get_settings

# Season the scheduled pipeline refreshes (mirrors the `incremental` CLI).
# Defaults to the calendar year and can be pinned with F1_CURRENT_SEASON.
CURRENT_SEASON = get_settings().current_season

# Race pace is only comparable inside one set of technical regulations. The
# ground-effect cars arrived in 2022, so do not pool older seasons by default.
PACE_PROFILE_FROM_SEASON = 2022

# Any season from 2006 onward can be backfilled independently from Dagster.
FIRST_SEASON = 2006

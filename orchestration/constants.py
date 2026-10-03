"""Shared orchestration settings that do not require loading the dbt manifest."""

from ingestion.config import FIRST_SEASON as INGESTION_FIRST_SEASON
from ingestion.config import get_settings

FIRST_SEASON = INGESTION_FIRST_SEASON

# Season the scheduled pipeline refreshes (mirrors the `incremental` CLI).
# Defaults to 2026 and can be pinned to 2024 or 2025 with F1_CURRENT_SEASON.
CURRENT_SEASON = get_settings().current_season

PACE_PROFILE_FROM_SEASON = FIRST_SEASON

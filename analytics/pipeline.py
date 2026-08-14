"""Materialise the global driver-rating mart from warehouse tables."""

from __future__ import annotations

import pandas as pd
from ingestion.config import Settings, get_settings
from ingestion.loaders.warehouse import read_query, replace_table
from ingestion.logging import get_logger

from analytics.ratings import compute_ratings

log = get_logger(__name__)

GAPS_QUERY = """
    select driver_id, teammate_id, pace_gap, season
    from intermediate.int_teammate_quali_gaps
"""

DRIVERS_QUERY = """
    select driver_id, driver_name, nationality
    from staging.stg_drivers
"""


def build_driver_ratings(settings: Settings | None = None) -> pd.DataFrame:
    """Compute the global rating and write it to ``marts.driver_ratings``.

    Returns the materialised DataFrame.
    """
    settings = settings or get_settings()

    gaps = read_query(GAPS_QUERY, settings)
    drivers = read_query(DRIVERS_QUERY, settings)

    result = compute_ratings(gaps)
    ratings = result.ratings

    # Per-driver comparison span from the gap data.
    span = (
        gaps.groupby("driver_id")
        .agg(
            first_season=("season", "min"),
            last_season=("season", "max"),
            n_seasons=("season", "nunique"),
        )
        .reset_index()
    )

    enriched = (
        ratings.merge(drivers, on="driver_id", how="left")
        .merge(span, on="driver_id", how="left")
        .loc[
            :,
            [
                "rank",
                "driver_id",
                "driver_name",
                "nationality",
                "rating",
                "pace_deficit",
                "n_comparisons",
                "n_seasons",
                "first_season",
                "last_season",
            ],
        ]
    )

    replace_table(enriched, schema="marts", table="driver_ratings", settings=settings)
    log.info(
        "ratings.materialised",
        drivers=len(enriched),
        converged=result.converged,
        iterations=result.iterations,
        component=result.main_component_size,
    )
    return enriched

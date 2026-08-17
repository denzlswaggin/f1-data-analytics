"""Materialise the driver-rating and race-replay marts from warehouse tables."""

from __future__ import annotations

import pandas as pd
from ingestion.config import Settings, get_settings
from ingestion.loaders.warehouse import read_query, replace_table
from ingestion.logging import get_logger

from analytics.ratings import compute_ratings
from analytics.replay import resample_race

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


def _replay_positions_query(season: int, rnd: int) -> str:
    return f"""
        select driver_code, session_time_sec, x, y
        from staging.stg_positions
        where season = {int(season)} and round = {int(rnd)} and session = 'R'
    """


def _replay_laps_query(season: int, rnd: int) -> str:
    return f"""
        select driver_code, lap_number, lap_start_sec, lap_time_sec
        from staging.stg_laps
        where season = {int(season)} and round = {int(rnd)} and session = 'R'
    """


def _build_one_replay(
    season: int,
    rnd: int,
    tick_s: float,
    retire_buffer_s: float,
    max_linger_s: float,
    settings: Settings,
) -> pd.DataFrame:
    """Resample one race into a replay frame (with season/round), no warehouse write.

    Resamples every car onto a shared time grid (see ``analytics.replay``). Kept
    lean (no per-row names/colours — those join client-side from a tiny driver-meta
    query) so the browser payload stays small. Empty (0 rows, right columns) if the
    race has no positions/laps ingested yet.
    """
    positions = read_query(_replay_positions_query(season, rnd), settings)
    laps = read_query(_replay_laps_query(season, rnd), settings)
    replay = resample_race(
        positions, laps, tick_s=tick_s, retire_buffer_s=retire_buffer_s, max_linger_s=max_linger_s
    )
    replay.insert(0, "season", season)
    replay.insert(1, "round", rnd)
    return replay


def build_race_replay(
    season: int,
    rnd: int,
    tick_s: float = 1.0,
    retire_buffer_s: float | None = None,
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Build the replay mart for a single race, fully replacing ``marts.race_replay``.

    Note this *replaces* the mart with just this race — use ``build_race_replays``
    to keep several races in the table for the dashboard. ``retire_buffer_s``
    defaults to ``settings.replay_retire_buffer_s``. Returns the frame.
    """
    settings = settings or get_settings()
    buf = retire_buffer_s if retire_buffer_s is not None else settings.replay_retire_buffer_s
    replay = _build_one_replay(
        season, rnd, tick_s, buf, settings.replay_retire_max_linger_s, settings
    )
    replace_table(replay, schema="marts", table="race_replay", settings=settings)
    log.info(
        "replay.materialised",
        season=season,
        round=rnd,
        rows=len(replay),
        drivers=replay["driver_code"].nunique() if not replay.empty else 0,
    )
    return replay


def build_race_replays(
    season: int,
    rounds: list[int],
    tick_s: float = 1.0,
    retire_buffer_s: float | None = None,
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Build the replay mart for several races at once (one ``marts.race_replay``).

    Builds each round and replaces the mart with their union, so the dashboard can
    offer a race picker. Rounds without positions/laps ingested contribute nothing.
    ``retire_buffer_s`` defaults to ``settings.replay_retire_buffer_s``. Returns the
    combined frame.
    """
    settings = settings or get_settings()
    buf = retire_buffer_s if retire_buffer_s is not None else settings.replay_retire_buffer_s
    linger = settings.replay_retire_max_linger_s
    frames = [_build_one_replay(season, rnd, tick_s, buf, linger, settings) for rnd in rounds]
    non_empty = [f for f in frames if not f.empty]
    combined = (
        pd.concat(non_empty, ignore_index=True)
        if non_empty
        else (frames[0] if frames else _build_one_replay(season, 0, tick_s, buf, linger, settings))
    )
    replace_table(combined, schema="marts", table="race_replay", settings=settings)
    log.info(
        "replay.materialised_season",
        season=season,
        rounds=len(rounds),
        races_with_data=len(non_empty),
        rows=len(combined),
    )
    return combined

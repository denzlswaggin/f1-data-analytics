"""Materialise the driver-rating and race-replay marts from warehouse tables."""

from __future__ import annotations

import pandas as pd
from ingestion.config import Settings, get_settings
from ingestion.loaders.warehouse import read_query, replace_table
from ingestion.logging import get_logger

from analytics.overtakes import detect_overtakes
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


def build_all_replays(
    tick_s: float = 1.0, retire_buffer_s: float | None = None, settings: Settings | None = None
) -> pd.DataFrame:
    """Build the replay mart for EVERY race with position data (all seasons).

    Reads the distinct ``(season, round)`` pairs from ``stg_positions`` and replaces
    ``marts.race_replay`` with their union, so the picker can span seasons (e.g. a
    2024 race alongside 2026). Returns the combined frame.
    """
    settings = settings or get_settings()
    buf = retire_buffer_s if retire_buffer_s is not None else settings.replay_retire_buffer_s
    linger = settings.replay_retire_max_linger_s
    pairs = read_query(
        "select distinct season, round from staging.stg_positions where session = 'R' "
        "order by season, round",
        settings,
    )
    specs = [(int(s), int(r)) for s, r in zip(pairs["season"], pairs["round"], strict=True)]
    frames = [_build_one_replay(s, r, tick_s, buf, linger, settings) for s, r in specs]
    non_empty = [f for f in frames if not f.empty]
    combined = (
        pd.concat(non_empty, ignore_index=True)
        if non_empty
        else _build_one_replay(0, 0, tick_s, buf, linger, settings)
    )
    replace_table(combined, schema="marts", table="race_replay", settings=settings)
    log.info("replay.materialised_all", races=len(non_empty), rows=len(combined))
    return combined


def _overtakes_query(season: int, rnd: int) -> str:
    return f"""
        select driver_code, t_s, x, y, running_order, gap_to_ahead_s
        from marts.race_replay
        where season = {int(season)} and round = {int(rnd)}
    """


def _build_one_overtakes(season: int, rnd: int, settings: Settings) -> pd.DataFrame:
    """Detect one race's overtakes from ``marts.race_replay`` (with season/round).

    Reads the already-built replay feed (so the passes align exactly with the
    animation) and runs the pure detector. Empty (0 rows, right columns) if the race
    has no replay rows or no clean passes are found.
    """
    replay = read_query(_overtakes_query(season, rnd), settings)
    passes = detect_overtakes(
        replay,
        battle_gap_s=settings.overtake_battle_gap_s,
        persist_s=settings.overtake_persist_s,
        start_guard_s=settings.overtake_start_guard_s,
        proximity_frac=settings.overtake_proximity_frac,
    )
    passes.insert(0, "season", season)
    passes.insert(1, "round", rnd)
    return passes


def build_race_overtakes(season: int, rnd: int, settings: Settings | None = None) -> pd.DataFrame:
    """Build the overtakes mart for a single race, replacing ``marts.race_overtakes``.

    Like ``build_race_replay`` this *replaces* the whole mart with just this race —
    use ``build_race_overtakes_season`` / ``build_all_overtakes`` to keep several
    races for the dashboard. Returns the frame.
    """
    settings = settings or get_settings()
    passes = _build_one_overtakes(season, rnd, settings)
    replace_table(passes, schema="marts", table="race_overtakes", settings=settings)
    log.info("overtakes.materialised", season=season, round=rnd, passes=len(passes))
    return passes


def build_race_overtakes_season(season: int, settings: Settings | None = None) -> pd.DataFrame:
    """Build the overtakes mart for every round of ``season`` present in the replay mart.

    Reads the rounds that actually exist in ``marts.race_replay`` for the season
    (overtakes depend on the replay having been built), detects each, and replaces
    ``marts.race_overtakes`` with their union. Returns the combined frame.
    """
    settings = settings or get_settings()
    rounds = read_query(
        f"select distinct round from marts.race_replay where season = {int(season)} order by round",
        settings,
    )
    specs = [int(r) for r in rounds["round"]]
    frames = [_build_one_overtakes(season, r, settings) for r in specs]
    non_empty = [f for f in frames if not f.empty]
    combined = (
        pd.concat(non_empty, ignore_index=True)
        if non_empty
        else (frames[0] if frames else _build_one_overtakes(season, 0, settings))
    )
    replace_table(combined, schema="marts", table="race_overtakes", settings=settings)
    log.info(
        "overtakes.materialised_season",
        season=season,
        rounds=len(specs),
        races_with_passes=len(non_empty),
        passes=len(combined),
    )
    return combined


def build_all_overtakes(settings: Settings | None = None) -> pd.DataFrame:
    """Build the overtakes mart for EVERY race in ``marts.race_replay`` (all seasons).

    Mirrors ``build_all_replays`` so the picker's overtake lane spans seasons.
    Returns the combined frame.
    """
    settings = settings or get_settings()
    pairs = read_query(
        "select distinct season, round from marts.race_replay order by season, round",
        settings,
    )
    specs = [(int(s), int(r)) for s, r in zip(pairs["season"], pairs["round"], strict=True)]
    frames = [_build_one_overtakes(s, r, settings) for s, r in specs]
    non_empty = [f for f in frames if not f.empty]
    combined = (
        pd.concat(non_empty, ignore_index=True)
        if non_empty
        else (frames[0] if frames else _build_one_overtakes(0, 0, settings))
    )
    replace_table(combined, schema="marts", table="race_overtakes", settings=settings)
    log.info("overtakes.materialised_all", races=len(non_empty), passes=len(combined))
    return combined

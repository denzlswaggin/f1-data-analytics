"""Materialise the rating, pace-profile and race-replay marts from warehouse tables."""

from __future__ import annotations

import pandas as pd
from ingestion.config import Settings, get_settings
from ingestion.loaders.warehouse import read_query, replace_table, replace_table_partition
from ingestion.logging import get_logger

from analytics.overtakes import detect_overtakes
from analytics.pace_consistency import PaceConsistencyResult, analyse_pace_consistency
from analytics.pace_profile import build_pace_profile
from analytics.pit_timing import PitTimingSensitivityResult, analyse_pit_timing_sensitivity
from analytics.pit_window import analyse_pit_windows
from analytics.race_control_impact import RaceControlImpactResult, analyse_race_control_impact
from analytics.ratings import compute_ratings
from analytics.ratings_v2 import cluster_bootstrap_dynamic_ratings, compute_dynamic_ratings
from analytics.ratings_v3 import V3ExperimentResult, evaluate_v3_experiment
from analytics.replay import IncompleteReplayError, resample_race, validate_replay_sources
from analytics.traffic import TrafficPaceResult, analyse_traffic_adjusted_pace
from analytics.tyre_warmup import TyreWarmupResult, analyse_tyre_warmup
from analytics.validation import bootstrap_ratings

log = get_logger(__name__)

GAPS_QUERY = """
    select driver_id, teammate_id, pace_gap, season
    from intermediate.int_teammate_quali_gaps
"""

DRIVERS_QUERY = """
    select driver_id, driver_name, nationality
    from staging.stg_drivers
"""

GAPS_V2_QUERY = """
    select race_key, driver_id, teammate_id, pace_gap, season, common_session
    from intermediate.int_teammate_quali_gaps
"""

RACE_GAPS_V3_QUERY = """
    select race_key, driver_id, teammate_id, pace_gap, season, n_laps
    from intermediate.int_teammate_race_gaps
"""


def build_driver_ratings(
    settings: Settings | None = None, *, n_boot: int = 300, bootstrap_seed: int = 0
) -> pd.DataFrame:
    """Compute the global rating and write it to ``marts.driver_ratings``.

    Returns the materialised DataFrame.
    """
    settings = settings or get_settings()

    gaps = read_query(GAPS_QUERY, settings)
    drivers = read_query(DRIVERS_QUERY, settings)

    result = compute_ratings(gaps)
    ratings = result.ratings
    uncertainty = bootstrap_ratings(gaps, n_boot=n_boot, seed=bootstrap_seed).loc[
        :, ["driver_id", "rating_lo", "rating_hi", "n_boot"]
    ]

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
        .merge(uncertainty, on="driver_id", how="left")
        .loc[
            :,
            [
                "rank",
                "driver_id",
                "driver_name",
                "nationality",
                "rating",
                "rating_lo",
                "rating_hi",
                "n_boot",
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


def build_driver_ratings_v2(
    settings: Settings | None = None,
    *,
    n_boot: int = 100,
    bootstrap_seed: int = 0,
    prior_weight: float = 8.0,
    temporal_weight: float = 48.0,
) -> pd.DataFrame:
    """Build season-specific dynamic ratings into ``marts.driver_ratings_v2``."""
    settings = settings or get_settings()
    gaps = read_query(GAPS_V2_QUERY, settings)
    drivers = read_query(DRIVERS_QUERY, settings)
    fit = compute_dynamic_ratings(
        gaps,
        prior_weight=prior_weight,
        temporal_weight=temporal_weight,
    )
    intervals = cluster_bootstrap_dynamic_ratings(
        gaps,
        n_boot=n_boot,
        seed=bootstrap_seed,
        prior_weight=prior_weight,
        temporal_weight=temporal_weight,
    )
    enriched = (
        fit.ratings.merge(drivers, on="driver_id", how="left")
        .merge(intervals, on=["driver_id", "season"], how="left")
        .loc[
            :,
            [
                "season",
                "rank",
                "driver_id",
                "driver_name",
                "nationality",
                "rating",
                "rating_lo",
                "rating_hi",
                "n_boot",
                "pace_deficit",
                "form_delta",
                "n_comparisons",
            ],
        ]
    )
    replace_table(enriched, schema="marts", table="driver_ratings_v2", settings=settings)
    log.info(
        "ratings_v2.materialised",
        rows=len(enriched),
        drivers=enriched["driver_id"].nunique(),
        seasons=enriched["season"].nunique(),
        converged=fit.converged,
        iterations=fit.iterations,
    )
    return enriched


def build_driver_ratings_v3(
    settings: Settings | None = None,
    *,
    final_holdout_season: int = 2026,
    min_train_seasons: int = 3,
    n_boot: int = 100,
    seed: int = 0,
) -> V3ExperimentResult:
    """Materialise the opt-in V3 model and its honest evaluation artifacts.

    V1 and V2 remain untouched.  ``marts.driver_ratings_v3`` is a research
    output, while the validation and ablation tables preserve the evidence
    needed to decide whether it should ever be promoted.
    """
    settings = settings or get_settings()
    qualifying = read_query(GAPS_V2_QUERY, settings)
    race = read_query(RACE_GAPS_V3_QUERY, settings)
    drivers = read_query(DRIVERS_QUERY, settings)
    result = evaluate_v3_experiment(
        qualifying,
        race,
        final_holdout_season=final_holdout_season,
        min_train_seasons=min_train_seasons,
        n_boot=n_boot,
        seed=seed,
    )
    ratings = result.ratings.merge(drivers, on="driver_id", how="left").loc[
        :,
        [
            "season",
            "rank",
            "driver_id",
            "driver_name",
            "nationality",
            "rating",
            "rating_lo",
            "rating_hi",
            "n_boot",
            "pace_deficit",
            "quali_rating",
            "race_rating",
            "discipline_delta",
            "form_delta",
            "n_quali_comparisons",
            "n_race_comparisons",
        ],
    ]
    materialised = V3ExperimentResult(
        ratings=ratings,
        validation=result.validation,
        ablation=result.ablation,
        selected_parameters=result.selected_parameters,
        holdout_status=result.holdout_status,
        recommended_for_promotion=result.recommended_for_promotion,
    )
    replace_table(ratings, schema="marts", table="driver_ratings_v3", settings=settings)
    replace_table(
        result.validation, schema="marts", table="driver_ratings_v3_validation", settings=settings
    )
    replace_table(
        result.ablation, schema="marts", table="driver_ratings_v3_ablation", settings=settings
    )
    log.info(
        "ratings_v3.materialised",
        rows=len(ratings),
        parameters=result.selected_parameters.label,
        holdout_status=result.holdout_status,
        recommended_for_promotion=result.recommended_for_promotion,
    )
    return materialised


def _race_gaps_query(from_season: int | None, to_season: int | None) -> str:
    where = []
    if from_season is not None:
        where.append(f"season >= {int(from_season)}")
    if to_season is not None:
        where.append(f"season <= {int(to_season)}")
    clause = f" where {' and '.join(where)}" if where else ""
    return (
        "select driver_id, teammate_id, pace_gap, season "
        f"from intermediate.int_teammate_race_gaps{clause}"
    )


def build_driver_pace_profile(
    from_season: int | None = None,
    to_season: int | None = None,
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Solve the race-pace rating alongside qualifying and write ``marts.driver_pace_profile``.

    ``from_season``/``to_season`` bound the *race* gaps (FastF1 laps cover far
    fewer seasons than qualifying, and race pace is only comparable within one
    regulation era). The qualifying gaps are read unbounded and matched to
    whatever seasons survive inside :func:`analytics.pace_profile.build_pace_profile`,
    so the two ratings always describe the same population.

    Returns the materialised DataFrame.
    """
    settings = settings or get_settings()

    race_gaps = read_query(_race_gaps_query(from_season, to_season), settings)
    quali_gaps = read_query(GAPS_QUERY, settings)
    drivers = read_query(DRIVERS_QUERY, settings)

    result = build_pace_profile(quali_gaps, race_gaps)

    # Season span from the race gaps — the binding side of the comparison.
    span = (
        race_gaps.groupby("driver_id")
        .agg(
            first_season=("season", "min"),
            last_season=("season", "max"),
            n_seasons=("season", "nunique"),
        )
        .reset_index()
    )

    enriched = (
        result.profile.merge(drivers, on="driver_id", how="left")
        .merge(span, on="driver_id", how="left")
        .loc[
            :,
            [
                "delta_rank",
                "driver_id",
                "driver_name",
                "nationality",
                "quali_rating",
                "race_rating",
                "delta",
                "quali_rank",
                "race_rank",
                "n_quali_comparisons",
                "n_race_comparisons",
                "n_seasons",
                "first_season",
                "last_season",
            ],
        ]
    )

    replace_table(enriched, schema="marts", table="driver_pace_profile", settings=settings)
    log.info(
        "pace_profile.materialised",
        drivers=len(enriched),
        seasons=result.seasons,
        quali_converged=result.quali.converged,
        race_converged=result.race.converged,
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
        select
            driver_code,
            lap_number,
            lap_start_sec,
            lap_time_sec,
            stint,
            compound,
            tyre_life
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
    validate_replay_sources(positions, laps)
    replay = resample_race(
        positions,
        laps,
        tick_s=tick_s,
        retire_buffer_s=retire_buffer_s,
        max_linger_s=max_linger_s,
        max_position_gap_s=settings.replay_max_position_gap_s,
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


def build_race_replay_incremental(
    season: int,
    rnd: int,
    tick_s: float = 1.0,
    retire_buffer_s: float | None = None,
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Build and replace exactly one race in ``marts.race_replay``.

    Unlike the legacy single-race helper, this preserves every other race in
    the mart. It is therefore safe for unattended round-level refreshes and for
    targeted corrections of an already materialised race.
    """
    settings = settings or get_settings()
    buf = retire_buffer_s if retire_buffer_s is not None else settings.replay_retire_buffer_s
    replay = _build_one_replay(
        season, rnd, tick_s, buf, settings.replay_retire_max_linger_s, settings
    )
    replace_table_partition(
        replay,
        schema="marts",
        table="race_replay",
        partition={"season": season, "round": rnd},
        settings=settings,
    )
    log.info(
        "replay.materialised_partition",
        season=season,
        round=rnd,
        rows=len(replay),
        drivers=replay["driver_code"].nunique() if not replay.empty else 0,
    )
    return replay


def _build_replay_frames(
    specs: list[tuple[int, int]],
    tick_s: float,
    retire_buffer_s: float,
    max_linger_s: float,
    settings: Settings,
) -> list[pd.DataFrame]:
    """Build complete replay partitions and skip known-truncated source feeds."""
    frames: list[pd.DataFrame] = []
    for season, rnd in specs:
        try:
            frames.append(
                _build_one_replay(
                    season,
                    rnd,
                    tick_s,
                    retire_buffer_s,
                    max_linger_s,
                    settings,
                )
            )
        except IncompleteReplayError as exc:
            log.warning(
                "replay.partition_skipped",
                season=season,
                round=rnd,
                reason=str(exc),
            )
    return frames


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
    specs = [(season, rnd) for rnd in rounds]
    frames = _build_replay_frames(specs, tick_s, buf, linger, settings)
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
    frames = _build_replay_frames(specs, tick_s, buf, linger, settings)
    non_empty = [f for f in frames if not f.empty]
    combined = (
        pd.concat(non_empty, ignore_index=True)
        if non_empty
        else _build_one_replay(0, 0, tick_s, buf, linger, settings)
    )
    replace_table(combined, schema="marts", table="race_replay", settings=settings)
    log.info("replay.materialised_all", races=len(non_empty), rows=len(combined))
    return combined


def _traffic_scope_query(table: str, season: int | None, rnd: int | None) -> str:
    where = ""
    if season is not None:
        where = f" where season = {int(season)}"
        if rnd is not None:
            where += f" and round = {int(rnd)}"
    return f"select * from marts.{table}{where}"


def _build_traffic_adjusted_scope(
    season: int | None,
    rnd: int | None,
    settings: Settings,
) -> TrafficPaceResult:
    laps = read_query(_traffic_scope_query("mart_lap_times", season, rnd), settings)
    replay = read_query(_traffic_scope_query("race_replay", season, rnd), settings)
    return analyse_traffic_adjusted_pace(laps, replay)


def _replace_traffic_tables(result: TrafficPaceResult, settings: Settings) -> None:
    replace_table(
        result.evidence,
        schema="marts",
        table="traffic_adjusted_laps",
        settings=settings,
    )
    replace_table(
        result.summary,
        schema="marts",
        table="traffic_adjusted_pace",
        settings=settings,
    )


def build_traffic_adjusted_pace(
    season: int,
    rnd: int,
    settings: Settings | None = None,
) -> TrafficPaceResult:
    """Build one race's traffic pace marts, replacing their full contents."""
    settings = settings or get_settings()
    result = _build_traffic_adjusted_scope(season, rnd, settings)
    _replace_traffic_tables(result, settings)
    log.info(
        "traffic_pace.materialised",
        season=season,
        round=rnd,
        evidence_laps=len(result.evidence),
        drivers=len(result.summary),
    )
    return result


def build_traffic_adjusted_pace_incremental(
    season: int,
    rnd: int,
    settings: Settings | None = None,
) -> TrafficPaceResult:
    """Recalculate one race while preserving every other mart partition."""
    settings = settings or get_settings()
    result = _build_traffic_adjusted_scope(season, rnd, settings)
    partition: dict[str, object] = {"season": season, "round": rnd}
    replace_table_partition(
        result.evidence,
        schema="marts",
        table="traffic_adjusted_laps",
        partition=partition,
        settings=settings,
    )
    replace_table_partition(
        result.summary,
        schema="marts",
        table="traffic_adjusted_pace",
        partition=partition,
        settings=settings,
    )
    log.info(
        "traffic_pace.materialised_partition",
        season=season,
        round=rnd,
        evidence_laps=len(result.evidence),
        drivers=len(result.summary),
    )
    return result


def build_all_traffic_adjusted_pace(
    settings: Settings | None = None,
) -> TrafficPaceResult:
    """Build traffic pace marts for every race present in the replay mart."""
    settings = settings or get_settings()
    result = _build_traffic_adjusted_scope(None, None, settings)
    _replace_traffic_tables(result, settings)
    races = result.summary[["season", "round"]].drop_duplicates().shape[0]
    log.info(
        "traffic_pace.materialised_all",
        races=races,
        evidence_laps=len(result.evidence),
        drivers=len(result.summary),
    )
    return result


def _pace_consistency_query(season: int | None, rnd: int | None) -> str:
    where = ""
    if season is not None:
        where = f" where traffic.season = {int(season)}"
        if rnd is not None:
            where += f" and traffic.round = {int(rnd)}"
    return f"""
        select
            traffic.*,
            coalesce(codes.driver_name, traffic.driver_code) as driver_name
        from marts.traffic_adjusted_laps as traffic
        left join staging.stg_driver_codes as codes
            on codes.season = traffic.season
            and codes.driver_code = traffic.driver_code
        {where}
    """


def _build_pace_consistency_scope(
    season: int | None,
    rnd: int | None,
    settings: Settings,
) -> PaceConsistencyResult:
    traffic_laps = read_query(_pace_consistency_query(season, rnd), settings)
    return analyse_pace_consistency(traffic_laps)


def _replace_pace_consistency_tables(result: PaceConsistencyResult, settings: Settings) -> None:
    replace_table(result.summary, schema="marts", table="pace_consistency", settings=settings)
    replace_table(
        result.laps,
        schema="marts",
        table="pace_consistency_laps",
        settings=settings,
    )


def build_pace_consistency(
    season: int,
    rnd: int,
    settings: Settings | None = None,
) -> PaceConsistencyResult:
    """Build one race's pace-consistency marts, replacing their full contents."""
    settings = settings or get_settings()
    result = _build_pace_consistency_scope(season, rnd, settings)
    _replace_pace_consistency_tables(result, settings)
    log.info(
        "pace_consistency.materialised",
        season=season,
        round=rnd,
        drivers=len(result.summary),
        evidence_laps=len(result.laps),
    )
    return result


def build_pace_consistency_incremental(
    season: int,
    rnd: int,
    settings: Settings | None = None,
) -> PaceConsistencyResult:
    """Recalculate one race while preserving every other consistency partition."""
    settings = settings or get_settings()
    result = _build_pace_consistency_scope(season, rnd, settings)
    partition: dict[str, object] = {"season": season, "round": rnd}
    replace_table_partition(
        result.summary,
        schema="marts",
        table="pace_consistency",
        partition=partition,
        settings=settings,
    )
    replace_table_partition(
        result.laps,
        schema="marts",
        table="pace_consistency_laps",
        partition=partition,
        settings=settings,
    )
    log.info(
        "pace_consistency.materialised_partition",
        season=season,
        round=rnd,
        drivers=len(result.summary),
        evidence_laps=len(result.laps),
    )
    return result


def build_all_pace_consistency(
    settings: Settings | None = None,
) -> PaceConsistencyResult:
    """Build pace consistency for every race with traffic-adjusted laps."""
    settings = settings or get_settings()
    result = _build_pace_consistency_scope(None, None, settings)
    _replace_pace_consistency_tables(result, settings)
    races = result.summary[["season", "round"]].drop_duplicates().shape[0]
    log.info(
        "pace_consistency.materialised_all",
        races=races,
        drivers=len(result.summary),
        evidence_laps=len(result.laps),
    )
    return result


def _tyre_warmup_laps_query(season: int | None, rnd: int | None) -> str:
    scope = _pit_window_scope_clause(season, rnd)
    return f"""
        select
            laps.season,
            laps.round,
            races.race_name,
            laps.driver_code,
            coalesce(codes.driver_name, laps.driver_code) as driver_name,
            laps.team,
            laps.lap_number,
            laps.stint,
            laps.compound,
            laps.tyre_life,
            laps.is_fresh_tyre,
            laps.lap_time_sec,
            laps.track_status
        from staging.stg_laps as laps
        left join staging.stg_races as races
            on races.season = laps.season and races.round = laps.round
        left join staging.stg_driver_codes as codes
            on codes.season = laps.season and codes.driver_code = laps.driver_code
        where laps.session = 'R'{scope}
    """


def _build_tyre_warmup_scope(
    season: int | None,
    rnd: int | None,
    settings: Settings,
) -> TyreWarmupResult:
    laps = read_query(_tyre_warmup_laps_query(season, rnd), settings)
    traffic_laps = read_query(_traffic_scope_query("traffic_adjusted_laps", season, rnd), settings)
    return analyse_tyre_warmup(laps, traffic_laps)


def _replace_tyre_warmup_tables(result: TyreWarmupResult, settings: Settings) -> None:
    replace_table(result.summary, schema="marts", table="tyre_warmup", settings=settings)
    replace_table(result.laps, schema="marts", table="tyre_warmup_laps", settings=settings)


def build_tyre_warmup(
    season: int,
    rnd: int,
    settings: Settings | None = None,
) -> TyreWarmupResult:
    """Build one race's tyre warm-up marts, replacing their full contents."""
    settings = settings or get_settings()
    result = _build_tyre_warmup_scope(season, rnd, settings)
    _replace_tyre_warmup_tables(result, settings)
    log.info(
        "tyre_warmup.materialised",
        season=season,
        round=rnd,
        stints=len(result.summary),
        evidence_laps=len(result.laps),
    )
    return result


def build_tyre_warmup_incremental(
    season: int,
    rnd: int,
    settings: Settings | None = None,
) -> TyreWarmupResult:
    """Recalculate one race while preserving every other warm-up partition."""
    settings = settings or get_settings()
    result = _build_tyre_warmup_scope(season, rnd, settings)
    partition: dict[str, object] = {"season": season, "round": rnd}
    replace_table_partition(
        result.summary,
        schema="marts",
        table="tyre_warmup",
        partition=partition,
        settings=settings,
    )
    replace_table_partition(
        result.laps,
        schema="marts",
        table="tyre_warmup_laps",
        partition=partition,
        settings=settings,
    )
    log.info(
        "tyre_warmup.materialised_partition",
        season=season,
        round=rnd,
        stints=len(result.summary),
        evidence_laps=len(result.laps),
    )
    return result


def build_all_tyre_warmup(
    settings: Settings | None = None,
) -> TyreWarmupResult:
    """Build tyre warm-up marts for every race with traffic evidence."""
    settings = settings or get_settings()
    result = _build_tyre_warmup_scope(None, None, settings)
    _replace_tyre_warmup_tables(result, settings)
    races = result.summary[["season", "round"]].drop_duplicates().shape[0]
    log.info(
        "tyre_warmup.materialised_all",
        races=races,
        stints=len(result.summary),
        evidence_laps=len(result.laps),
    )
    return result


def _pit_window_scope_clause(season: int | None, rnd: int | None) -> str:
    if season is None:
        return ""
    clause = f" and laps.season = {int(season)}"
    if rnd is not None:
        clause += f" and laps.round = {int(rnd)}"
    return clause


def _pit_window_laps_query(season: int | None, rnd: int | None) -> str:
    scope = _pit_window_scope_clause(season, rnd)
    return f"""
        select
            laps.season,
            laps.round,
            races.race_name,
            laps.driver_code,
            coalesce(codes.driver_name, laps.driver_code) as driver_name,
            laps.team,
            laps.lap_number,
            laps.stint,
            laps.compound,
            laps.is_fresh_tyre,
            laps.tyre_life,
            laps.position,
            laps.lap_start_sec,
            laps.lap_time_sec,
            laps.track_status
        from staging.stg_laps as laps
        left join staging.stg_races as races
            on races.season = laps.season and races.round = laps.round
        left join staging.stg_driver_codes as codes
            on codes.season = laps.season and codes.driver_code = laps.driver_code
        where laps.session = 'R'{scope}
    """


def _pit_window_stops_query(season: int | None, rnd: int | None) -> str:
    where = ""
    if season is not None:
        where = f" where stops.season = {int(season)}"
        if rnd is not None:
            where += f" and stops.round = {int(rnd)}"
    return f"""
        select
            stops.season,
            stops.round,
            codes.driver_code,
            stops.pit_lap,
            stops.duration_sec
        from staging.stg_pitstops as stops
        inner join staging.stg_driver_codes as codes
            on codes.season = stops.season and codes.driver_id = stops.driver_id
        {where}
    """


def _build_pit_window_scope(
    season: int | None,
    rnd: int | None,
    settings: Settings,
) -> pd.DataFrame:
    laps = read_query(_pit_window_laps_query(season, rnd), settings)
    stops = read_query(_pit_window_stops_query(season, rnd), settings)
    return analyse_pit_windows(laps, stops)


def build_pit_window_effectiveness(
    season: int,
    rnd: int,
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Build one race's pairwise pit-window mart, replacing its full contents."""
    settings = settings or get_settings()
    result = _build_pit_window_scope(season, rnd, settings)
    replace_table(
        result,
        schema="marts",
        table="pit_window_effectiveness",
        settings=settings,
    )
    log.info("pit_window.materialised", season=season, round=rnd, matchups=len(result))
    return result


def build_pit_window_effectiveness_incremental(
    season: int,
    rnd: int,
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Recalculate one race while preserving every other pit-window partition."""
    settings = settings or get_settings()
    result = _build_pit_window_scope(season, rnd, settings)
    replace_table_partition(
        result,
        schema="marts",
        table="pit_window_effectiveness",
        partition={"season": season, "round": rnd},
        settings=settings,
    )
    log.info(
        "pit_window.materialised_partition",
        season=season,
        round=rnd,
        matchups=len(result),
    )
    return result


def build_all_pit_window_effectiveness(
    settings: Settings | None = None,
) -> pd.DataFrame:
    """Build the pairwise pit-window mart for every loaded FastF1 race."""
    settings = settings or get_settings()
    result = _build_pit_window_scope(None, None, settings)
    replace_table(
        result,
        schema="marts",
        table="pit_window_effectiveness",
        settings=settings,
    )
    races = result[["season", "round"]].drop_duplicates().shape[0]
    log.info("pit_window.materialised_all", races=races, matchups=len(result))
    return result


def _build_pit_timing_scope(
    season: int | None,
    rnd: int | None,
    settings: Settings,
) -> PitTimingSensitivityResult:
    laps = read_query(_tyre_warmup_laps_query(season, rnd), settings)
    replay = read_query(_traffic_scope_query("race_replay", season, rnd), settings)
    stops = read_query(_pit_window_stops_query(season, rnd), settings)
    return analyse_pit_timing_sensitivity(laps, replay, stops)


def _replace_pit_timing_tables(result: PitTimingSensitivityResult, settings: Settings) -> None:
    replace_table(
        result.summary,
        schema="marts",
        table="pit_timing_sensitivity",
        settings=settings,
    )
    replace_table(
        result.scenarios,
        schema="marts",
        table="pit_timing_scenarios",
        settings=settings,
    )


def build_pit_timing_sensitivity(
    season: int,
    rnd: int,
    settings: Settings | None = None,
) -> PitTimingSensitivityResult:
    """Build one race's pit-timing marts, replacing their full contents."""
    settings = settings or get_settings()
    result = _build_pit_timing_scope(season, rnd, settings)
    _replace_pit_timing_tables(result, settings)
    log.info(
        "pit_timing.materialised",
        season=season,
        round=rnd,
        stops=len(result.summary),
        scenarios=len(result.scenarios),
    )
    return result


def build_pit_timing_sensitivity_incremental(
    season: int,
    rnd: int,
    settings: Settings | None = None,
) -> PitTimingSensitivityResult:
    """Recalculate one race while preserving every other pit-timing partition."""
    settings = settings or get_settings()
    result = _build_pit_timing_scope(season, rnd, settings)
    partition: dict[str, object] = {"season": season, "round": rnd}
    replace_table_partition(
        result.summary,
        schema="marts",
        table="pit_timing_sensitivity",
        partition=partition,
        settings=settings,
    )
    replace_table_partition(
        result.scenarios,
        schema="marts",
        table="pit_timing_scenarios",
        partition=partition,
        settings=settings,
    )
    log.info(
        "pit_timing.materialised_partition",
        season=season,
        round=rnd,
        stops=len(result.summary),
        scenarios=len(result.scenarios),
    )
    return result


def build_all_pit_timing_sensitivity(
    settings: Settings | None = None,
) -> PitTimingSensitivityResult:
    """Build pit-timing sensitivity for every race in the replay mart."""
    settings = settings or get_settings()
    result = _build_pit_timing_scope(None, None, settings)
    _replace_pit_timing_tables(result, settings)
    races = result.summary[["season", "round"]].drop_duplicates().shape[0]
    log.info(
        "pit_timing.materialised_all",
        races=races,
        stops=len(result.summary),
        scenarios=len(result.scenarios),
    )
    return result


def _race_control_scope_clause(alias: str, season: int | None, rnd: int | None) -> str:
    if season is None:
        return ""
    clause = f" and {alias}.season = {int(season)}"
    if rnd is not None:
        clause += f" and {alias}.round = {int(rnd)}"
    return clause


def _race_control_replay_query(season: int | None, rnd: int | None) -> str:
    scope = _race_control_scope_clause("replay", season, rnd)
    return f"""
        with teams as (
            select season, round, driver_code, max(team) as team
            from staging.stg_laps
            where session = 'R'
            group by season, round, driver_code
        )
        select
            replay.season,
            replay.round,
            races.race_name,
            replay.driver_code,
            coalesce(codes.driver_name, replay.driver_code) as driver_name,
            teams.team,
            replay.t_s,
            replay.lap_number,
            replay.stint,
            replay.compound,
            replay.tyre_life,
            replay.running_order,
            replay.gap_to_leader_s
        from marts.race_replay as replay
        left join staging.stg_races as races
            on races.season = replay.season and races.round = replay.round
        left join staging.stg_driver_codes as codes
            on codes.season = replay.season and codes.driver_code = replay.driver_code
        left join teams
            on teams.season = replay.season
            and teams.round = replay.round
            and teams.driver_code = replay.driver_code
        where true{scope}
    """


def _race_control_messages_query(season: int | None, rnd: int | None) -> str:
    scope = _race_control_scope_clause("messages", season, rnd)
    return f"""
        with race_windows as (
            select season, round, min(lap_start_sec) as race_start_sec
            from staging.stg_laps
            where session = 'R'
            group by season, round
        )
        select
            messages.season,
            messages.round,
            races.race_name,
            messages.session_time_sec - windows.race_start_sec as t_s,
            messages.category,
            messages.flag,
            messages.message,
            messages.lap
        from staging.stg_race_control as messages
        inner join race_windows as windows
            on windows.season = messages.season and windows.round = messages.round
        left join staging.stg_races as races
            on races.season = messages.season and races.round = messages.round
        where messages.session = 'R'{scope}
    """


def _race_control_laps_query(season: int | None, rnd: int | None) -> str:
    scope = _race_control_scope_clause("laps", season, rnd)
    return f"""
        select laps.season, laps.round, laps.lap_number, laps.track_status
        from staging.stg_laps as laps
        where laps.session = 'R'{scope}
    """


def _build_race_control_impact_scope(
    season: int | None,
    rnd: int | None,
    settings: Settings,
) -> RaceControlImpactResult:
    replay = read_query(_race_control_replay_query(season, rnd), settings)
    messages = read_query(_race_control_messages_query(season, rnd), settings)
    laps = read_query(_race_control_laps_query(season, rnd), settings)
    return analyse_race_control_impact(replay, messages, laps)


def _replace_race_control_impact_tables(
    result: RaceControlImpactResult, settings: Settings
) -> None:
    replace_table(result.events, schema="marts", table="race_control_events", settings=settings)
    replace_table(result.evidence, schema="marts", table="race_control_impact", settings=settings)


def build_race_control_impact(
    season: int,
    rnd: int,
    settings: Settings | None = None,
) -> RaceControlImpactResult:
    """Build one race's race-control impact mart, replacing its contents."""
    settings = settings or get_settings()
    result = _build_race_control_impact_scope(season, rnd, settings)
    _replace_race_control_impact_tables(result, settings)
    log.info(
        "race_control_impact.materialised",
        season=season,
        round=rnd,
        events=len(result.events),
        evidence=len(result.evidence),
    )
    return result


def build_race_control_impact_incremental(
    season: int,
    rnd: int,
    settings: Settings | None = None,
) -> RaceControlImpactResult:
    """Recalculate one race while preserving other race-control partitions."""
    settings = settings or get_settings()
    result = _build_race_control_impact_scope(season, rnd, settings)
    replace_table_partition(
        result.events,
        schema="marts",
        table="race_control_events",
        partition={"season": season, "round": rnd},
        settings=settings,
    )
    replace_table_partition(
        result.evidence,
        schema="marts",
        table="race_control_impact",
        partition={"season": season, "round": rnd},
        settings=settings,
    )
    log.info(
        "race_control_impact.materialised_partition",
        season=season,
        round=rnd,
        events=len(result.events),
        evidence=len(result.evidence),
    )
    return result


def build_all_race_control_impact(
    settings: Settings | None = None,
) -> RaceControlImpactResult:
    """Build race-control impact for every race present in the replay mart."""
    settings = settings or get_settings()
    result = _build_race_control_impact_scope(None, None, settings)
    _replace_race_control_impact_tables(result, settings)
    races = result.events[["season", "round"]].drop_duplicates().shape[0]
    log.info(
        "race_control_impact.materialised_all",
        races=races,
        events=len(result.events),
        evidence=len(result.evidence),
    )
    return result


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


def build_race_overtakes_incremental(
    season: int, rnd: int, settings: Settings | None = None
) -> pd.DataFrame:
    """Detect and replace exactly one race in ``marts.race_overtakes``."""
    settings = settings or get_settings()
    passes = _build_one_overtakes(season, rnd, settings)
    replace_table_partition(
        passes,
        schema="marts",
        table="race_overtakes",
        partition={"season": season, "round": rnd},
        settings=settings,
    )
    log.info("overtakes.materialised_partition", season=season, round=rnd, passes=len(passes))
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

"""Software-defined assets for the F1 pipeline.

Ingestion assets are keyed ``["raw", <table>]`` so they line up with the dbt
sources of the same name — dagster-dbt then wires the dbt models downstream
automatically. The Python rating solver depends on the dbt intermediate model.
"""

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from analytics.pipeline import (
    build_all_pace_consistency,
    build_all_pit_lap_context,
    build_all_pit_timing_sensitivity,
    build_all_pit_window_effectiveness,
    build_all_race_control_impact,
    build_all_racecraft_battles,
    build_all_traffic_adjusted_pace,
    build_all_tyre_warmup,
    build_driver_pace_profile,
    build_driver_ratings,
    build_driver_ratings_v2,
    build_driver_ratings_v3,
    build_race_overtakes_season,
    build_race_replays,
)
from dagster import (
    AssetCheckResult,
    AssetExecutionContext,
    AssetKey,
    Backoff,
    Jitter,
    MaterializeResult,
    RetryPolicy,
    StaticPartitionsDefinition,
    asset,
    asset_check,
)
from dagster_dbt import (
    DagsterDbtTranslator,
    DbtCliResource,
    DbtProject,
    dbt_assets,
)
from ingestion.health import evaluate_pipeline_health
from ingestion.loaders.warehouse import read_query
from ingestion.pipeline import (
    ingest_ergast_laps,
    ingest_laps,
    ingest_pitstops,
    ingest_positions,
    ingest_race_control,
    ingest_resource,
    ingest_team_radio,
    ingest_telemetry,
    ingest_weather,
    season_rounds,
)

from orchestration.constants import CURRENT_SEASON, FIRST_SEASON, PACE_PROFILE_FROM_SEASON

SEASON_PARTITIONS = StaticPartitionsDefinition(
    [str(year) for year in range(FIRST_SEASON, CURRENT_SEASON + 1)]
)

# Ingestion assets hit external APIs (Jolpica / FastF1 / OpenF1), which fail
# transiently. Retry with exponential backoff + jitter before the run fails.
INGEST_RETRY = RetryPolicy(
    max_retries=3, delay=10, backoff=Backoff.EXPONENTIAL, jitter=Jitter.PLUS_MINUS
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_PROJECT_DIR = _REPO_ROOT / "warehouse" / "dbt"

dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR)
dbt_project.prepare_if_dev()


# --- Ingestion assets (keyed to dbt sources) --------------------------------
@asset(
    key=["raw", "races"],
    partitions_def=SEASON_PARTITIONS,
    group_name="ingest",
    compute_kind="jolpica",
    retry_policy=INGEST_RETRY,
)
def raw_races(context: AssetExecutionContext) -> MaterializeResult:
    season = int(context.partition_key)
    rows = ingest_resource("races", season)
    return MaterializeResult(metadata={"rows": rows, "season": season})


@asset(
    key=["raw", "results"],
    partitions_def=SEASON_PARTITIONS,
    group_name="ingest",
    compute_kind="jolpica",
    retry_policy=INGEST_RETRY,
)
def raw_results(context: AssetExecutionContext) -> MaterializeResult:
    season = int(context.partition_key)
    rows = ingest_resource("results", season)
    return MaterializeResult(metadata={"rows": rows, "season": season})


@asset(
    key=["raw", "qualifying"],
    partitions_def=SEASON_PARTITIONS,
    group_name="ingest",
    compute_kind="jolpica",
    retry_policy=INGEST_RETRY,
)
def raw_qualifying(context: AssetExecutionContext) -> MaterializeResult:
    season = int(context.partition_key)
    rows = ingest_resource("qualifying", season)
    return MaterializeResult(metadata={"rows": rows, "season": season})


@asset(
    key=["raw", "laps"],
    partitions_def=SEASON_PARTITIONS,
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="fastf1",
    retry_policy=INGEST_RETRY,
)
def raw_laps(context: AssetExecutionContext) -> MaterializeResult:
    season = int(context.partition_key)
    rounds = season_rounds(season, completed_only=True)
    rows = ingest_laps(season, rounds, "R")
    return MaterializeResult(metadata={"rows": rows, "season": season})


@asset(
    key=["raw", "pitstops"],
    partitions_def=SEASON_PARTITIONS,
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="jolpica",
    retry_policy=INGEST_RETRY,
)
def raw_pitstops(context: AssetExecutionContext) -> MaterializeResult:
    season = int(context.partition_key)
    rounds = season_rounds(season, completed_only=True)
    rows = ingest_pitstops(season, rounds)
    return MaterializeResult(metadata={"rows": rows, "season": season})


@asset(
    key=["raw", "ergast_laps"],
    partitions_def=SEASON_PARTITIONS,
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="jolpica",
    retry_policy=INGEST_RETRY,
)
def raw_ergast_laps(context: AssetExecutionContext) -> MaterializeResult:
    season = int(context.partition_key)
    rounds = season_rounds(season, completed_only=True)
    rows = ingest_ergast_laps(season, rounds)
    return MaterializeResult(metadata={"rows": rows, "season": season})


@asset(
    key=["raw", "weather"],
    partitions_def=SEASON_PARTITIONS,
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="fastf1",
    retry_policy=INGEST_RETRY,
)
def raw_weather(context: AssetExecutionContext) -> MaterializeResult:
    season = int(context.partition_key)
    rounds = season_rounds(season, completed_only=True)
    rows = ingest_weather(season, rounds, "R")
    return MaterializeResult(metadata={"rows": rows, "season": season})


@asset(
    key=["raw", "telemetry"],
    partitions_def=SEASON_PARTITIONS,
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="fastf1",
    retry_policy=INGEST_RETRY,
)
def raw_telemetry(context: AssetExecutionContext) -> MaterializeResult:
    # Heavy: resampled telemetry for every race lap of the season. Kept out of the
    # weekly refresh job (see definitions.py) — materialise on demand.
    season = int(context.partition_key)
    rounds = season_rounds(season, completed_only=True)
    rows = ingest_telemetry(season, rounds, "R")
    return MaterializeResult(metadata={"rows": rows, "season": season})


@asset(
    key=["raw", "positions"],
    partitions_def=SEASON_PARTITIONS,
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="fastf1",
    retry_policy=INGEST_RETRY,
)
def raw_positions(context: AssetExecutionContext) -> MaterializeResult:
    # Heavy: time-stamped car positions for the race-replay map. Like telemetry it's
    # kept out of the weekly refresh job (see definitions.py) — materialise on demand.
    season = int(context.partition_key)
    rounds = season_rounds(season, completed_only=True)
    rows = ingest_positions(season, rounds, "R")
    return MaterializeResult(metadata={"rows": rows, "season": season})


@asset(
    key=["raw", "race_control"],
    partitions_def=SEASON_PARTITIONS,
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="fastf1",
    retry_policy=INGEST_RETRY,
)
def raw_race_control(context: AssetExecutionContext) -> MaterializeResult:
    # Official race-control messages for the replay feed. Needs the telemetry cache
    # for the session-time reference, so it's kept out of the weekly job too.
    season = int(context.partition_key)
    rounds = season_rounds(season, completed_only=True)
    rows = ingest_race_control(season, rounds, "R")
    return MaterializeResult(metadata={"rows": rows, "season": season})


@asset(
    key=["raw", "team_radio"],
    partitions_def=SEASON_PARTITIONS,
    deps=[AssetKey(["raw", "races"])],
    group_name="ingest",
    compute_kind="openf1",
    retry_policy=INGEST_RETRY,
)
def raw_team_radio(context: AssetExecutionContext) -> MaterializeResult:
    # OpenF1 team-radio clips for the replay player. Aligns via the telemetry cache,
    # so it's kept out of the weekly job too. Coverage is partial.
    season = int(context.partition_key)
    rounds = season_rounds(season, completed_only=True)
    rows = ingest_team_radio(season, rounds, "R")
    return MaterializeResult(metadata={"rows": rows, "season": season})


# --- dbt models -------------------------------------------------------------
class F1DbtTranslator(DagsterDbtTranslator):
    """Map dbt sources to the ingestion assets' ``["raw", <table>]`` keys."""

    def get_asset_key(self, dbt_resource_props: Mapping[str, Any]) -> AssetKey:
        if dbt_resource_props["resource_type"] == "source":
            return AssetKey(["raw", dbt_resource_props["name"]])
        if dbt_resource_props["resource_type"] == "seed":
            # CI fixtures are dbt resources too, but they must not collide with
            # the real raw ingestion assets in the Dagster graph.
            return AssetKey(["ci_seed", dbt_resource_props["name"]])
        return super().get_asset_key(dbt_resource_props)


@dbt_assets(manifest=dbt_project.manifest_path, dagster_dbt_translator=F1DbtTranslator())
def dbt_models(context: AssetExecutionContext, dbt: DbtCliResource) -> Iterator[Any]:
    yield from dbt.cli(["build"], context=context).stream()


# --- Analytics: the global rating solver ------------------------------------
@asset(
    deps=[AssetKey(["int_teammate_quali_gaps"]), AssetKey(["stg_drivers"])],
    group_name="analytics",
    compute_kind="python",
)
def driver_ratings() -> MaterializeResult:
    df = build_driver_ratings()
    top = df.iloc[0]
    return MaterializeResult(
        metadata={"drivers": len(df), "fastest": f"{top['driver_name']} ({top['rating']:.3f})"}
    )


@asset(
    deps=[AssetKey(["int_teammate_quali_gaps"]), AssetKey(["stg_drivers"])],
    group_name="analytics",
    compute_kind="python",
)
def driver_ratings_v2() -> MaterializeResult:
    df = build_driver_ratings_v2()
    latest = int(df["season"].max())
    leader = df[df["season"] == latest].iloc[0]
    return MaterializeResult(
        metadata={
            "driver_seasons": len(df),
            "latest_season": latest,
            "leader": f"{leader['driver_name']} ({leader['rating']:.3f})",
        }
    )


@asset(
    deps=[
        AssetKey(["int_teammate_quali_gaps"]),
        AssetKey(["int_teammate_race_gaps"]),
        AssetKey(["stg_drivers"]),
    ],
    group_name="analytics",
    compute_kind="python",
)
def driver_ratings_v3() -> MaterializeResult:
    """Materialise V3 as an experiment, including holdout and ablation evidence."""
    result = build_driver_ratings_v3()
    return MaterializeResult(
        metadata={
            "driver_seasons": len(result.ratings),
            "parameters": result.selected_parameters.label,
            "holdout_status": result.holdout_status,
            "recommended_for_promotion": result.recommended_for_promotion,
        }
    )


@asset(
    deps=[
        AssetKey(["int_teammate_quali_gaps"]),
        AssetKey(["int_teammate_race_gaps"]),
        AssetKey(["stg_drivers"]),
    ],
    group_name="analytics",
    compute_kind="python",
)
def driver_pace_profile() -> MaterializeResult:
    # Solve the race-pace rating and set it against qualifying over the same seasons.
    df = build_driver_pace_profile(from_season=PACE_PROFILE_FROM_SEASON)
    if df.empty:
        return MaterializeResult(metadata={"drivers": 0, "note": "no race gaps ingested yet"})
    racer = df.iloc[0]
    return MaterializeResult(
        metadata={
            "drivers": len(df),
            "from_season": PACE_PROFILE_FROM_SEASON,
            "biggest_racer": f"{racer['driver_name']} ({racer['delta']:+.3f})",
        }
    )


@asset(
    deps=[AssetKey(["stg_positions"]), AssetKey(["stg_laps"])],
    group_name="analytics",
    compute_kind="python",
)
def race_replay() -> MaterializeResult:
    # Resample every completed round into the animated-replay mart.
    rounds = season_rounds(CURRENT_SEASON, completed_only=True)
    df = build_race_replays(CURRENT_SEASON, rounds)
    races = int(df["round"].nunique()) if not df.empty else 0
    return MaterializeResult(metadata={"rows": len(df), "races": races, "season": CURRENT_SEASON})


@asset(
    deps=[AssetKey(["stg_laps"]), AssetKey(["stg_pitstops"]), AssetKey(["stg_driver_codes"])],
    group_name="analytics",
    compute_kind="python",
)
def pit_lap_context() -> MaterializeResult:
    result = build_all_pit_lap_context()
    return MaterializeResult(
        metadata={"laps": len(result), "pit_laps": int(result["is_pit_boundary"].sum())}
    )


@asset(
    deps=[AssetKey(["race_replay"]), AssetKey(["mart_lap_times"]), AssetKey(["pit_lap_context"])],
    group_name="analytics",
    compute_kind="python",
)
def traffic_adjusted_pace() -> MaterializeResult:
    result = build_all_traffic_adjusted_pace()
    publishable = int(result.summary["traffic_adjusted_pace_delta_sec"].notna().sum())
    races = int(result.summary[["season", "round"]].drop_duplicates().shape[0])
    return MaterializeResult(
        metadata={
            "drivers": len(result.summary),
            "publishable_driver_races": publishable,
            "evidence_laps": len(result.evidence),
            "races": races,
        }
    )


@asset(
    deps=[AssetKey(["traffic_adjusted_pace"]), AssetKey(["stg_driver_codes"])],
    group_name="analytics",
    compute_kind="python",
)
def pace_consistency() -> MaterializeResult:
    result = build_all_pace_consistency()
    eligible = int(result.summary["consistency_eligible"].sum()) if not result.summary.empty else 0
    races = int(
        result.summary.loc[result.summary["consistency_eligible"], ["season", "round"]]
        .drop_duplicates()
        .shape[0]
    )
    return MaterializeResult(
        metadata={
            "driver_races": len(result.summary),
            "eligible_driver_races": eligible,
            "eligible_races": races,
            "evidence_laps": len(result.laps),
        }
    )


@asset(
    deps=[
        AssetKey(["traffic_adjusted_pace"]),
        AssetKey(["pit_lap_context"]),
        AssetKey(["stg_laps"]),
        AssetKey(["stg_driver_codes"]),
        AssetKey(["stg_races"]),
    ],
    group_name="analytics",
    compute_kind="python",
)
def tyre_warmup() -> MaterializeResult:
    result = build_all_tyre_warmup()
    eligible = int(result.summary["warmup_eligible"].sum()) if not result.summary.empty else 0
    races = int(
        result.summary.loc[result.summary["warmup_eligible"], ["season", "round"]]
        .drop_duplicates()
        .shape[0]
    )
    return MaterializeResult(
        metadata={
            "stints": len(result.summary),
            "eligible_stints": eligible,
            "eligible_races": races,
            "evidence_laps": len(result.laps),
        }
    )


@asset(
    deps=[
        AssetKey(["stg_laps"]),
        AssetKey(["stg_pitstops"]),
        AssetKey(["pit_lap_context"]),
        AssetKey(["stg_driver_codes"]),
        AssetKey(["stg_races"]),
    ],
    group_name="analytics",
    compute_kind="python",
)
def pit_window_effectiveness() -> MaterializeResult:
    df = build_all_pit_window_effectiveness()
    eligible = int(df["eligible"].sum()) if not df.empty else 0
    races = int(df.loc[df["eligible"], ["season", "round"]].drop_duplicates().shape[0])
    return MaterializeResult(
        metadata={
            "matchups": len(df),
            "eligible_matchups": eligible,
            "eligible_races": races,
        }
    )


@asset(
    deps=[
        AssetKey(["race_replay"]),
        AssetKey(["stg_laps"]),
        AssetKey(["stg_pitstops"]),
        AssetKey(["pit_lap_context"]),
        AssetKey(["stg_driver_codes"]),
        AssetKey(["stg_races"]),
    ],
    group_name="analytics",
    compute_kind="python",
)
def pit_timing_sensitivity() -> MaterializeResult:
    result = build_all_pit_timing_sensitivity()
    eligible = int(result.summary["eligible"].sum()) if not result.summary.empty else 0
    races = int(
        result.summary.loc[result.summary["eligible"], ["season", "round"]]
        .drop_duplicates()
        .shape[0]
    )
    return MaterializeResult(
        metadata={
            "stops": len(result.summary),
            "eligible_stops": eligible,
            "eligible_races": races,
            "scenarios": len(result.scenarios),
        }
    )


@asset(
    deps=[
        AssetKey(["race_replay"]),
        AssetKey(["stg_race_control"]),
        AssetKey(["stg_laps"]),
        AssetKey(["stg_driver_codes"]),
        AssetKey(["stg_races"]),
    ],
    group_name="analytics",
    compute_kind="python",
)
def race_control_impact() -> MaterializeResult:
    result = build_all_race_control_impact()
    eligible = int(result.events["eligible"].sum()) if not result.events.empty else 0
    return MaterializeResult(
        metadata={
            "events": len(result.events),
            "eligible_events": eligible,
            "driver_observations": len(result.evidence),
        }
    )


@asset(
    deps=[AssetKey(["race_replay"])],
    group_name="analytics",
    compute_kind="python",
)
def race_overtakes() -> MaterializeResult:
    # Detect on-track overtakes from the replay mart (every round built above).
    df = build_race_overtakes_season(CURRENT_SEASON)
    races = int(df["round"].nunique()) if not df.empty else 0
    return MaterializeResult(metadata={"passes": len(df), "races": races, "season": CURRENT_SEASON})


@asset(
    deps=[
        AssetKey(["race_replay"]),
        AssetKey(["race_overtakes"]),
        AssetKey(["pit_lap_context"]),
        AssetKey(["stg_laps"]),
        AssetKey(["stg_driver_codes"]),
        AssetKey(["stg_races"]),
    ],
    group_name="analytics",
    compute_kind="python",
)
def racecraft_battle_conversion() -> MaterializeResult:
    result = build_all_racecraft_battles()
    eligible = int(result.battles["eligible"].sum()) if not result.battles.empty else 0
    races = int(result.summary[["season", "round"]].drop_duplicates().shape[0])
    return MaterializeResult(
        metadata={
            "battles": len(result.battles),
            "eligible_battles": eligible,
            "driver_races": len(result.summary),
            "races": races,
        }
    )


# --- Asset checks (data-quality gates surfaced in the Dagster UI) ------------
@asset_check(asset=raw_races, name="current_season_present", blocking=True)
def raw_races_current_season_present() -> AssetCheckResult:
    """The current season's race schedule must have landed (else downstream is stale)."""
    df = read_query(f"select count(*) as n from raw.races where season = {CURRENT_SEASON}")
    n = int(df["n"].iloc[0])
    return AssetCheckResult(passed=n > 0, metadata={"rows_current_season": n})


@asset_check(asset=raw_results, name="current_load_is_fresh", blocking=True)
def raw_results_current_load_is_fresh() -> AssetCheckResult:
    """The unattended weekly pipeline must have succeeded in the last eight days."""
    checks = evaluate_pipeline_health(season=CURRENT_SEASON, max_age_hours=192)
    passed = all(check.passed for check in checks)
    return AssetCheckResult(
        passed=passed,
        metadata={check.name: check.detail for check in checks},
    )


@asset_check(asset=driver_ratings, name="ratings_are_sane", blocking=True)
def driver_ratings_are_sane() -> AssetCheckResult:
    """Ratings must be unique, non-null, and carry valid uncertainty intervals."""
    df = read_query(
        "select count(*) as n, "
        "count(*) filter (where rating is null) as null_ratings, "
        "count(*) filter (where rating_lo is null or rating_hi is null) as null_intervals, "
        "count(*) filter (where rating_lo > rating_hi) as invalid_intervals, "
        "count(distinct driver_id) as distinct_ids "
        "from marts.driver_ratings"
    )
    n = int(df["n"].iloc[0])
    nulls = int(df["null_ratings"].iloc[0])
    null_intervals = int(df["null_intervals"].iloc[0])
    invalid_intervals = int(df["invalid_intervals"].iloc[0])
    distinct = int(df["distinct_ids"].iloc[0])
    return AssetCheckResult(
        passed=(
            n > 0
            and nulls == 0
            and null_intervals == 0
            and invalid_intervals == 0
            and distinct == n
        ),
        metadata={
            "rows": n,
            "null_ratings": nulls,
            "null_intervals": null_intervals,
            "invalid_intervals": invalid_intervals,
            "distinct_driver_ids": distinct,
        },
    )


@asset_check(asset=driver_ratings_v2, name="dynamic_ratings_are_sane", blocking=True)
def driver_ratings_v2_are_sane() -> AssetCheckResult:
    """Dynamic ratings must be unique per driver-season with valid intervals."""
    df = read_query(
        "select count(*) as n, count(distinct cast(season as varchar) || '-' || driver_id) as keys, "
        "count(*) filter (where rating is null or rating_lo is null or rating_hi is null) as nulls, "
        "count(*) filter (where rating_lo > rating or rating > rating_hi) as invalid "
        "from marts.driver_ratings_v2"
    )
    row = df.iloc[0]
    passed = (
        int(row["n"]) > 0
        and int(row["n"]) == int(row["keys"])
        and int(row["nulls"]) == 0
        and int(row["invalid"]) == 0
    )
    return AssetCheckResult(passed=passed, metadata=row.to_dict())


@asset_check(asset=driver_ratings_v3, name="experimental_ratings_are_sane", blocking=True)
def driver_ratings_v3_are_sane() -> AssetCheckResult:
    """V3 research rows must be unique and intervals must contain point estimates."""
    df = read_query(
        "select count(*) as n, count(distinct cast(season as varchar) || '-' || driver_id) as keys, "
        "count(*) filter (where rating is null or rating_lo is null or rating_hi is null) as nulls, "
        "count(*) filter (where rating_lo > rating or rating > rating_hi) as invalid "
        "from marts.driver_ratings_v3"
    )
    row = df.iloc[0]
    passed = (
        int(row["n"]) > 0
        and int(row["n"]) == int(row["keys"])
        and int(row["nulls"]) == 0
        and int(row["invalid"]) == 0
    )
    return AssetCheckResult(passed=passed, metadata=row.to_dict())


@asset_check(asset=driver_pace_profile, name="pace_profile_is_sane", blocking=True)
def driver_pace_profile_is_sane() -> AssetCheckResult:
    """One row per driver, no null deltas, and delta must equal race - quali exactly."""
    df = read_query(
        "select count(*) as n, "
        "count(*) filter (where delta is null) as null_deltas, "
        "count(distinct driver_id) as distinct_ids, "
        "max(abs(delta - (race_rating - quali_rating))) as max_delta_err "
        "from marts.driver_pace_profile"
    )
    n = int(df["n"].iloc[0])
    nulls = int(df["null_deltas"].iloc[0])
    distinct = int(df["distinct_ids"].iloc[0])
    err = float(df["max_delta_err"].iloc[0] or 0.0)
    return AssetCheckResult(
        passed=n > 0 and nulls == 0 and distinct == n and err < 1e-9,
        metadata={
            "rows": n,
            "null_deltas": nulls,
            "distinct_driver_ids": distinct,
            "max_delta_error": err,
        },
    )

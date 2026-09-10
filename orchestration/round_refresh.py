"""Round-level Dagster job for the unattended race-weekend refresh.

The asset graph remains the convenient season-backfill interface. This job is
the operational path: one explicit ``season/round/session`` partition ingests
only that race, refreshes dbt once, and replaces only that race in each
Python-built race-analysis mart.
"""

import time
from collections.abc import Callable

from analytics.pipeline import (
    build_driver_pace_profile,
    build_driver_ratings,
    build_driver_ratings_v2,
    build_pit_window_effectiveness_incremental,
    build_race_control_impact_incremental,
    build_race_overtakes_incremental,
    build_race_replay_incremental,
    build_traffic_adjusted_pace_incremental,
)
from dagster import (
    Failure,
    MultiPartitionKey,
    MultiPartitionsDefinition,
    OpExecutionContext,
    RunRequest,
    SkipReason,
    StaticPartitionsDefinition,
    job,
    op,
    schedule,
)
from ingestion.config import Settings, get_settings
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
    latest_completed_round,
)

from orchestration.constants import CURRENT_SEASON, FIRST_SEASON, PACE_PROFILE_FROM_SEASON

ROUND_PARTITIONS = MultiPartitionsDefinition(
    {
        "season": StaticPartitionsDefinition(
            [str(year) for year in range(FIRST_SEASON, CURRENT_SEASON + 1)]
        ),
        # Dagster supports exactly two multi-partition dimensions. Keep round
        # and session explicit in one composite dimension (for example 8:R).
        # Spare rounds avoid a code deploy if a future calendar grows.
        "round_session": StaticPartitionsDefinition([f"{rnd}:R" for rnd in range(1, 31)]),
    }
)


def _partition_values(context: OpExecutionContext) -> tuple[int, int, str]:
    key = context.partition_key
    if not isinstance(key, MultiPartitionKey):
        raise Failure("round refresh requires a season/round-session multi-partition key")
    dimensions = key.keys_by_dimension
    round_text, session = dimensions["round_session"].split(":", maxsplit=1)
    return int(dimensions["season"]), int(round_text), session


def _within_budget[T](
    context: OpExecutionContext,
    label: str,
    budget_seconds: float,
    function: Callable[[], T],
) -> T:
    started = time.perf_counter()
    result = function()
    duration = time.perf_counter() - started
    context.add_output_metadata(
        {
            "stage": label,
            "duration_seconds": round(duration, 3),
            "budget_seconds": budget_seconds,
            "budget_utilisation": round(duration / budget_seconds, 4),
        }
    )
    if duration > budget_seconds:
        raise Failure(
            f"{label} took {duration:.1f}s, exceeding its {budget_seconds:.1f}s performance budget",
            metadata={"duration_seconds": duration, "budget_seconds": budget_seconds},
        )
    return result


def _ingest_round(season: int, rnd: int, session: str, settings: Settings) -> dict[str, int]:
    """Ingest one race partition while refreshing the small season endpoints."""
    summary = {
        # These endpoints expose a season document, not a round endpoint. They
        # remain cheap enough to replace and keep corrections/results current.
        resource: ingest_resource(resource, season, settings=settings)
        for resource in ("races", "results", "qualifying")
    }
    summary.update(
        {
            "laps": ingest_laps(season, [rnd], session, settings),
            "pitstops": ingest_pitstops(season, [rnd], settings),
            "ergast_laps": ingest_ergast_laps(season, [rnd], settings),
            "weather": ingest_weather(season, [rnd], session, settings),
            "telemetry": ingest_telemetry(season, [rnd], session, settings),
            "positions": ingest_positions(season, [rnd], session, settings),
            "race_control": ingest_race_control(season, [rnd], session, settings),
            "team_radio": ingest_team_radio(season, [rnd], session, settings),
        }
    )
    return summary


@op
def ingest_round(context: OpExecutionContext) -> dict[str, int]:
    season, rnd, session = _partition_values(context)
    settings = get_settings()
    return _within_budget(
        context,
        "round_ingest",
        settings.round_ingest_budget_seconds,
        lambda: _ingest_round(season, rnd, session, settings),
    )


@op(required_resource_keys={"dbt"})
def transform_round(context: OpExecutionContext, summary: dict[str, int]) -> str:
    settings = get_settings()

    def run_dbt() -> str:
        context.log.info(
            "Building dbt models after ingesting %s source rows", sum(summary.values())
        )
        context.resources.dbt.cli(["build"], context=context).wait()
        return "dbt build completed"

    return _within_budget(
        context,
        "round_transform",
        settings.round_transform_budget_seconds,
        run_dbt,
    )


@op
def materialize_round_analytics(
    context: OpExecutionContext, _transform_status: str
) -> dict[str, int]:
    season, rnd, _session = _partition_values(context)
    settings = get_settings()

    return _within_budget(
        context,
        "round_analytics",
        settings.round_analytics_budget_seconds,
        lambda: _build_round_analytics(season, rnd, settings),
    )


def _build_round_analytics(season: int, rnd: int, settings: Settings) -> dict[str, int]:
    """Refresh every Python-built mart affected by a completed round."""
    ratings = build_driver_ratings(settings=settings)
    dynamic_ratings = build_driver_ratings_v2(settings=settings)
    pace_profile = build_driver_pace_profile(
        from_season=PACE_PROFILE_FROM_SEASON,
        settings=settings,
    )
    replay = build_race_replay_incremental(season, rnd, settings=settings)
    traffic = build_traffic_adjusted_pace_incremental(season, rnd, settings=settings)
    pit_windows = build_pit_window_effectiveness_incremental(season, rnd, settings=settings)
    race_control = build_race_control_impact_incremental(season, rnd, settings=settings)
    overtakes = build_race_overtakes_incremental(season, rnd, settings=settings)
    return {
        "ratings": len(ratings),
        "dynamic_ratings": len(dynamic_ratings),
        "pace_profiles": len(pace_profile),
        "replay_rows": len(replay),
        "traffic_pace_drivers": len(traffic.summary),
        "pit_window_matchups": len(pit_windows),
        "race_control_events": len(race_control.events),
        "race_control_observations": len(race_control.evidence),
        "overtakes": len(overtakes),
    }


@job(partitions_def=ROUND_PARTITIONS)
def round_refresh_job() -> None:
    """Refresh one requested race partition end to end."""
    materialize_round_analytics(transform_round(ingest_round()))


@schedule(job=round_refresh_job, cron_schedule="0 6 * * 1", name="latest_round_refresh")
def latest_round_schedule() -> RunRequest | SkipReason:
    """Refresh only the latest completed race each Monday."""
    settings = get_settings()
    rnd = latest_completed_round(CURRENT_SEASON, settings)
    if rnd is None:
        return SkipReason(
            f"No completed round found for {CURRENT_SEASON}; bootstrap raw.races first"
        )
    partition_key = MultiPartitionKey({"season": str(CURRENT_SEASON), "round_session": f"{rnd}:R"})
    return RunRequest(
        run_key=f"round-refresh-{CURRENT_SEASON}-{rnd}-R",
        partition_key=partition_key,
        tags={
            "f1/season": str(CURRENT_SEASON),
            "f1/round": str(rnd),
            "f1/session": "R",
            "dagster/max_runtime": str(int(settings.round_refresh_budget_seconds)),
        },
    )

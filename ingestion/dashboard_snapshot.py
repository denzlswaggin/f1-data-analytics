"""Build immutable DuckDB snapshots for the static Evidence dashboard.

The operational warehouse remains the system of record.  A dashboard build
consumes a compact, read-only snapshot instead of running a historical backfill
inside the Pages workflow.  Snapshots can be produced from either development
DuckDB or production Postgres and optionally published to object storage.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from sqlalchemy import create_engine, inspect, text

from ingestion.config import Settings, get_settings

DASHBOARD_SCHEMAS = ("staging", "intermediate", "marts")

# This is the serving contract, not merely a minimum snapshot smoke test. Every
# public Evidence source must be able to compile against a freshly exported
# database. Optional datasets still materialise an empty table with the declared
# columns, so their absence is always a broken pipeline rather than "no data".
DASHBOARD_CONTRACT: dict[tuple[str, str], set[str]] = {
    ("marts", "pit_lap_context"): {
        "season",
        "round",
        "driver_code",
        "lap_number",
        "is_pit_in_lap",
        "is_pit_out_lap",
        "is_pit_boundary",
        "pit_context_source",
        "pit_context_status",
        "pit_exclusion_reason",
    },
    ("staging", "stg_races"): {"season", "round", "race_name", "race_date"},
    ("staging", "stg_driver_codes"): {
        "season",
        "driver_code",
        "driver_id",
        "driver_name",
    },
    ("staging", "stg_results"): {
        "season",
        "round",
        "driver_code",
        "grid_position",
        "finish_position",
        "status",
        "is_classified",
    },
    ("staging", "stg_laps"): {
        "season",
        "round",
        "session",
        "driver_code",
        "team",
        "lap_number",
        "stint",
        "compound",
        "tyre_life",
        "lap_start_sec",
        "lap_time_sec",
    },
    ("staging", "stg_race_control"): {
        "season",
        "round",
        "session",
        "session_time_sec",
        "category",
        "flag",
        "scope",
        "message",
        "driver_code",
        "lap",
    },
    ("staging", "stg_team_radio"): {
        "season",
        "round",
        "session_time_sec",
        "session",
        "driver_code",
        "recording_url",
        "transcript",
    },
    ("staging", "stg_weather"): {
        "season",
        "round",
        "session",
        "time_sec",
        "air_temp",
        "track_temp",
        "humidity",
        "pressure",
        "wind_speed",
        "wind_direction",
        "is_raining",
    },
    ("staging", "constructor_colors"): {"team", "team_color"},
    ("intermediate", "int_teammate_quali_gaps"): {
        "race_key",
        "season",
        "driver_id",
        "teammate_id",
        "pace_gap",
    },
    ("intermediate", "int_teammate_race_gaps"): {
        "race_key",
        "season",
        "driver_id",
        "teammate_id",
        "pace_gap",
        "n_laps",
    },
    ("marts", "driver_ratings"): {
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
    },
    ("marts", "driver_ratings_v2"): {
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
    },
    ("marts", "driver_pace_profile"): {
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
    },
    ("marts", "mart_driver_season_pace"): {
        "driver_id",
        "driver_name",
        "season",
        "races_compared",
        "teammate_quali_wins",
        "teammate_win_pct",
        "mean_pace_gap",
        "stddev_pace_gap",
    },
    ("marts", "mart_lap_times"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "team",
        "lap_number",
        "stint",
        "compound",
        "tyre_life",
        "position",
        "lap_time_sec",
    },
    ("marts", "mart_pit_strategy"): {
        "season",
        "round",
        "race_name",
        "driver_id",
        "driver_name",
        "stop_number",
        "pit_lap",
        "duration_sec",
        "position_before",
        "position_after",
        "positions_gained",
    },
    ("marts", "mart_speed_trap"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "n_laps",
        "top_speed_kph",
        "avg_speed_kph",
    },
    ("marts", "mart_stint_strategy"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "stint",
        "compound",
        "start_lap",
        "end_lap",
        "stint_laps",
        "tyre_life_end",
        "started_fresh",
        "finish_position",
        "deg_sec_per_lap",
    },
    ("marts", "mart_tyre_degradation"): {
        "season",
        "round",
        "race_name",
        "compound",
        "n_laps",
        "deg_sec_per_lap",
        "best_lap_sec",
        "avg_lap_sec",
    },
    ("marts", "mart_weather_degradation"): {
        "season",
        "round",
        "race_name",
        "compound",
        "weather_bucket",
        "avg_track_temp",
        "avg_air_temp",
        "n_laps",
        "deg_sec_per_lap",
        "avg_lap_sec",
    },
    ("marts", "mart_lap_telemetry"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "lap_number",
        "compound",
        "distance_m",
        "speed_kph",
        "throttle",
        "brake",
        "drs",
        "gear",
        "x",
        "y",
    },
    ("marts", "race_replay"): {
        "season",
        "round",
        "driver_code",
        "t_s",
        "x",
        "y",
        "running_order",
        "gap_to_leader_s",
        "gap_to_ahead_s",
        "lap_number",
        "lap_progress",
        "stint",
        "compound",
        "tyre_life",
    },
    ("marts", "traffic_adjusted_laps"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "team",
        "lap_number",
        "stint",
        "compound",
        "tyre_life",
        "lap_time_sec",
        "context_samples",
        "valid_context_samples",
        "traffic_samples",
        "traffic_share",
        "clean_air_share",
        "replay_coverage_pct",
        "median_gap_to_ahead_s",
        "air_state",
        "peer_lap_avg_sec",
        "controlled_pace_delta_sec",
        "matched_clean_laps",
        "matched_clean_delta_sec",
        "paired_traffic_delta_sec",
    },
    ("marts", "traffic_adjusted_pace"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "team",
        "eligible_laps",
        "clean_air_laps",
        "traffic_laps",
        "mixed_laps",
        "matched_traffic_laps",
        "traffic_exposure_pct",
        "replay_coverage_pct",
        "observed_controlled_pace_delta_sec",
        "clean_air_controlled_pace_delta_sec",
        "traffic_adjusted_pace_delta_sec",
        "traffic_controlled_pace_delta_sec",
        "traffic_associated_delta_sec_per_lap",
        "traffic_associated_p25_sec",
        "traffic_associated_p75_sec",
        "confidence",
        "traffic_gap_threshold_s",
        "clean_air_gap_threshold_s",
        "methodology_version",
    },
    ("marts", "pace_consistency"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "candidate_laps",
        "modelled_laps",
        "excluded_laps",
        "candidate_stints",
        "modelled_stints",
        "robust_consistency_sec",
        "robust_consistency_pct",
        "p90_slow_tail_sec",
        "slow_lap_threshold_sec",
        "unexplained_slow_laps",
        "unexplained_slow_lap_share_pct",
        "unexplained_slow_lap_cost_sec",
        "slow_lap_cost_per_10_laps_sec",
        "worst_residual_sec",
        "replay_coverage_pct",
        "consistency_eligible",
        "exclusion_reason",
        "confidence",
        "methodology_version",
    },
    ("marts", "pace_consistency_laps"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "lap_number",
        "stint",
        "compound",
        "tyre_life",
        "lap_time_sec",
        "air_state",
        "replay_coverage_pct",
        "controlled_pace_delta_sec",
        "expected_controlled_pace_delta_sec",
        "pace_residual_sec",
        "absolute_residual_sec",
        "slow_lap_threshold_sec",
        "unexplained_slow_excess_sec",
        "is_unexplained_slow_lap",
        "lap_eligible",
        "lap_exclusion_reason",
        "stint_clean_laps",
        "stint_slope_sec_per_tyre_lap",
        "stint_intercept_sec",
        "methodology_version",
    },
    ("marts", "pit_timing_sensitivity"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "stop_number",
        "actual_pit_lap",
        "actual_out_lap",
        "pit_duration_sec",
        "official_pit_match",
        "old_stint",
        "new_stint",
        "old_compound",
        "new_compound",
        "new_tyre_fresh",
        "window_start_lap",
        "window_end_lap",
        "best_supported_shift_laps",
        "best_hypothetical_pit_lap",
        "estimated_gain_vs_actual_sec",
        "best_delta_p25_sec",
        "best_delta_p75_sec",
        "best_shift_win_pct",
        "best_earlier_delta_sec",
        "best_later_delta_sec",
        "supported_scenarios",
        "old_reference_laps",
        "new_mature_reference_laps",
        "warmup_profile_laps",
        "old_slope_sec_per_tyre_lap",
        "new_slope_sec_per_stint_lap",
        "old_model_mad_sec",
        "new_model_mad_sec",
        "replay_coverage_pct",
        "field_peer_count_median",
        "timing_signal",
        "eligible",
        "exclusion_reason",
        "confidence",
        "methodology_version",
    },
    ("marts", "pit_timing_scenarios"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "stop_number",
        "actual_pit_lap",
        "actual_out_lap",
        "shift_laps",
        "hypothetical_pit_lap",
        "hypothetical_out_lap",
        "estimated_cost_index_sec",
        "delta_vs_actual_sec",
        "estimated_gain_vs_actual_sec",
        "delta_p25_sec",
        "delta_p75_sec",
        "old_tyre_extension_laps",
        "supported",
        "exclusion_reason",
        "methodology_version",
    },
    ("marts", "tyre_warmup"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "stint",
        "compound",
        "is_fresh_tyre",
        "out_lap",
        "stint_start_lap",
        "stint_end_lap",
        "stint_laps",
        "contiguous_stint_transition",
        "clean_evaluation_laps",
        "traffic_evaluation_laps",
        "mature_reference_laps",
        "baseline_slope_sec_per_lap",
        "baseline_intercept_sec",
        "baseline_mad_sec",
        "first_flying_warmup_loss_sec",
        "second_flying_warmup_loss_sec",
        "first_two_lap_warmup_cost_sec",
        "stable_band_sec",
        "stable_window_start_lap",
        "time_to_pace_laps",
        "stable_pace_achieved",
        "right_censored",
        "observation_complete",
        "warmup_eligible",
        "crossover_eligible",
        "exclusion_reason",
        "confidence",
        "replay_coverage_pct",
        "methodology_version",
    },
    ("marts", "tyre_warmup_laps"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "stint",
        "compound",
        "is_fresh_tyre",
        "out_lap",
        "lap_number",
        "post_stop_offset",
        "tyre_life",
        "lap_time_sec",
        "track_status",
        "air_state",
        "replay_coverage_pct",
        "traffic_share",
        "median_gap_to_ahead_s",
        "controlled_pace_delta_sec",
        "expected_mature_delta_sec",
        "warmup_loss_sec",
        "used_for_baseline",
        "within_stable_band",
        "lap_eligible",
        "lap_exclusion_reason",
        "methodology_version",
    },
    ("marts", "pit_window_effectiveness"): {
        "season",
        "round",
        "race_name",
        "stop_number",
        "early_driver_code",
        "early_driver_name",
        "early_team",
        "late_driver_code",
        "late_driver_name",
        "late_team",
        "early_pit_lap",
        "late_pit_lap",
        "stop_separation_laps",
        "checkpoint_before_lap",
        "checkpoint_after_lap",
        "early_old_compound",
        "early_new_compound",
        "late_old_compound",
        "late_new_compound",
        "early_new_tyre_fresh",
        "late_new_tyre_fresh",
        "position_before_early",
        "position_before_late",
        "position_after_early",
        "position_after_late",
        "gap_before_sec",
        "gap_after_sec",
        "net_time_gain_sec",
        "early_stop_duration_sec",
        "late_stop_duration_sec",
        "stop_duration_delta_sec",
        "on_track_gain_sec",
        "position_flip",
        "window_green",
        "eligible",
        "exclusion_reason",
        "confidence",
        "opportunity_type",
        "outcome_label",
        "methodology_version",
    },
    ("marts", "race_control_events"): {
        "season",
        "round",
        "race_name",
        "event_id",
        "event_number",
        "event_type",
        "start_t_s",
        "end_t_s",
        "post_checkpoint_t_s",
        "deployment_lap",
        "end_lap",
        "post_checkpoint_lap",
        "duration_s",
        "event_status",
        "recovery_clean",
        "pre_driver_count",
        "post_driver_count",
        "eligible_driver_count",
        "intervention_stop_count",
        "recovery_stop_count",
        "position_gainer_count",
        "position_loser_count",
        "eligible",
        "exclusion_reason",
        "confidence",
        "methodology_version",
    },
    ("marts", "race_control_impact"): {
        "season",
        "round",
        "race_name",
        "event_id",
        "event_number",
        "event_type",
        "driver_code",
        "driver_name",
        "team",
        "position_before",
        "position_after",
        "positions_gained",
        "gap_to_leader_before_s",
        "gap_to_leader_after_s",
        "raw_gap_gain_s",
        "field_adjusted_gap_gain_s",
        "lap_before",
        "lap_after",
        "lap_deficit_before",
        "lap_deficit_after",
        "lap_deficit_changed",
        "stint_before",
        "stint_after",
        "compound_before",
        "compound_after",
        "tyre_life_before",
        "tyre_life_after",
        "pitted_during_intervention",
        "pitted_during_recovery",
        "stop_count",
        "tyre_changed_during_suspension",
        "active_after",
        "eligible",
        "exclusion_reason",
        "confidence",
        "outcome_label",
        "timing_before_offset_s",
        "timing_after_offset_s",
        "methodology_version",
    },
    ("marts", "race_overtakes"): {
        "season",
        "round",
        "t_s",
        "for_position",
        "passer_code",
        "passed_code",
        "gap_at_pass_s",
        "confidence",
        "evidence",
        "reason",
    },
    ("marts", "racecraft_battles"): {
        "season",
        "round",
        "race_name",
        "battle_id",
        "battle_number",
        "attacker_code",
        "attacker_name",
        "attacker_team",
        "defender_code",
        "defender_name",
        "defender_team",
        "same_team",
        "start_t_s",
        "end_t_s",
        "duration_s",
        "pressure_seconds",
        "contact_seconds",
        "start_lap",
        "end_lap",
        "laps_spanned",
        "position_contested",
        "valid_samples",
        "pressure_samples",
        "coverage_pct",
        "same_lap_deficit_share_pct",
        "min_gap_s",
        "median_gap_s",
        "outcome",
        "terminal_reason",
        "converted",
        "defender_retained",
        "pass_t_s",
        "pass_lap",
        "time_to_pass_s",
        "overtake_confidence",
        "overtake_reason",
        "quick_reversal",
        "reversal_t_s",
        "eligible",
        "exclusion_reason",
        "confidence",
        "pressure_gap_threshold_s",
        "minimum_pressure_s",
        "methodology_version",
    },
    ("marts", "racecraft_driver_summary"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "driver_name",
        "team",
        "attacking_opportunities",
        "converted_opportunities",
        "attacks_defended",
        "attack_conversion_pct",
        "attack_conversion_p05_pct",
        "attack_conversion_p95_pct",
        "attack_pressure_s",
        "distinct_defenders",
        "median_time_to_pass_s",
        "defensive_opportunities",
        "defences_held",
        "passes_conceded",
        "defence_hold_pct",
        "defence_hold_p05_pct",
        "defence_hold_p95_pct",
        "defensive_pressure_s",
        "distinct_attackers",
        "interrupted_attacks",
        "unresolved_attacks",
        "interrupted_defences",
        "unresolved_defences",
        "quick_reversals_made",
        "quick_reversals_conceded",
        "longest_battle_s",
        "offense_eligible",
        "defense_eligible",
        "offense_exclusion_reason",
        "defense_exclusion_reason",
        "offense_confidence",
        "defense_confidence",
        "confidence",
        "methodology_version",
    },
    ("marts", "mart_race_story"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "finish_position",
        "is_classified",
        "pace_samples",
        "controlled_pace_delta_sec",
        "pace_rank",
        "outcome_vs_pace",
        "story_label",
    },
    ("marts", "mart_adjusted_stint_degradation"): {
        "season",
        "round",
        "race_name",
        "driver_code",
        "stint",
        "compound",
        "comparable_laps",
        "stint_length",
        "adjusted_deg_sec_per_lap",
        "raw_deg_sec_per_lap",
        "late_stint_loss_sec",
        "cliff_signal",
    },
}

REQUIRED_TABLES = tuple(DASHBOARD_CONTRACT)


@dataclass(frozen=True)
class SnapshotManifest:
    """Metadata shipped next to one immutable dashboard database."""

    version: str
    generated_at: str
    source: str
    database_file: str
    sha256: str
    size_bytes: int
    latest_event_date: str | None
    table_rows: dict[str, int]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _scalar(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    row = connection.execute(query).fetchone()
    if row is None:
        raise ValueError(f"snapshot query returned no row: {query}")
    return row[0]


def _version(now: dt.datetime) -> str:
    revision = os.getenv("GITHUB_SHA", "local")[:8]
    return f"{now:%Y%m%dT%H%M%SZ}-{revision}"


def _copy_duckdb(source: Path, target: Path) -> dict[str, int]:
    if not source.is_file():
        raise FileNotFoundError(f"DuckDB warehouse does not exist: {source}")
    source_sql = str(source.resolve()).replace("'", "''")
    connection = duckdb.connect(str(target))
    rows: dict[str, int] = {}
    try:
        # dbt views in the development warehouse are bound to its normal `f1`
        # catalog name. Attach under that name, then materialize every relation so
        # the snapshot remains valid regardless of its eventual filename.
        connection.execute(f"ATTACH '{source_sql}' AS f1 (READ_ONLY)")
        tables = connection.execute(
            "select table_schema, table_name from information_schema.tables "
            "where table_catalog = 'f1' and table_schema in (?, ?, ?) "
            "order by table_schema, table_name",
            list(DASHBOARD_SCHEMAS),
        ).fetchall()
        for schema, table in tables:
            connection.execute(f"create schema if not exists {_quote(schema)}")
            qualified = f"{_quote(schema)}.{_quote(table)}"
            connection.execute(f"create table {qualified} as select * from f1.{qualified}")
            rows[f"{schema}.{table}"] = int(
                _scalar(connection, f"select count(*) from {qualified}")
            )
        connection.execute("detach f1")
    finally:
        connection.close()
    return rows


def _copy_postgres(settings: Settings, target: Path) -> dict[str, int]:
    engine = create_engine(settings.pg_dsn)
    target_connection = duckdb.connect(str(target))
    rows: dict[str, int] = {}
    try:
        inspector = inspect(engine)
        with engine.connect() as source_connection:
            for schema in DASHBOARD_SCHEMAS:
                target_connection.execute(f"create schema if not exists {_quote(schema)}")
                names = sorted(
                    set(inspector.get_table_names(schema=schema))
                    | set(inspector.get_view_names(schema=schema))
                )
                for table_name in names:
                    qualified = f"{_quote(schema)}.{_quote(table_name)}"
                    count = 0
                    first = True
                    query = text(f"select * from {qualified}")
                    for frame in pd.read_sql_query(query, source_connection, chunksize=50_000):
                        target_connection.register("snapshot_chunk", frame)
                        if first:
                            target_connection.execute(
                                f"create table {qualified} as select * from snapshot_chunk"
                            )
                            first = False
                        elif not frame.empty:
                            target_connection.execute(
                                f"insert into {qualified} by name select * from snapshot_chunk"
                            )
                        count += len(frame)
                        target_connection.unregister("snapshot_chunk")
                    rows[f"{schema}.{table_name}"] = count
    finally:
        target_connection.close()
        engine.dispose()
    return rows


def validate_dashboard_snapshot(path: Path) -> str | None:
    """Validate that a snapshot can compile every public dashboard source."""
    connection = duckdb.connect(str(path), read_only=True)
    try:
        available = {
            (str(schema), str(table))
            for schema, table in connection.execute(
                "select table_schema, table_name from information_schema.tables"
            ).fetchall()
        }
        missing = sorted(set(REQUIRED_TABLES) - available)
        if missing:
            raise ValueError(f"dashboard snapshot is missing required tables: {missing}")
        broken_columns: list[str] = []
        for (schema, table), required in DASHBOARD_CONTRACT.items():
            columns = {
                str(row[0])
                for row in connection.execute(
                    "select column_name from information_schema.columns "
                    "where table_schema = ? and table_name = ?",
                    [schema, table],
                ).fetchall()
            }
            missing_columns = sorted(required - columns)
            if missing_columns:
                broken_columns.append(f"{schema}.{table}: {missing_columns}")
        if broken_columns:
            raise ValueError(
                "dashboard snapshot has incompatible columns: " + "; ".join(broken_columns)
            )
        if _scalar(connection, "select count(*) from marts.driver_ratings") == 0:
            raise ValueError("dashboard snapshot contains no driver ratings")
        value = _scalar(
            connection,
            "select coalesce("
            "(select max(races.race_date) from staging.stg_races as races "
            "join (select distinct season, round from marts.mart_lap_times) as represented "
            "using (season, round)), "
            "(select max(race_date) from staging.stg_races)"
            ")",
        )
        return None if value is None else str(value)
    finally:
        connection.close()


def _write_snapshot_metadata(
    path: Path,
    *,
    version: str,
    generated_at: dt.datetime,
    source: str,
    latest_event_date: str | None,
) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute("create schema if not exists dashboard")
        connection.execute(
            "create table dashboard.snapshot_metadata as "
            "select ?::varchar as version, ?::timestamptz as generated_at, "
            "?::varchar as source, ?::date as latest_event_date",
            [version, generated_at, source, latest_event_date],
        )
    finally:
        connection.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(payload: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def _publish(path: Path, manifest_path: Path, publish_uri: str, version: str) -> None:
    import fsspec

    base = publish_uri.rstrip("/")
    filesystem, root = fsspec.core.url_to_fs(base)
    version_root = f"{root.rstrip('/')}/{version}"
    filesystem.makedirs(version_root, exist_ok=True)
    filesystem.put(str(path), f"{version_root}/{path.name}")
    filesystem.put(str(manifest_path), f"{version_root}/{manifest_path.name}")
    filesystem.put(str(manifest_path), f"{root.rstrip('/')}/latest.json")


def build_dashboard_snapshot(
    output_dir: Path,
    *,
    settings: Settings | None = None,
    version: str | None = None,
    publish_uri: str | None = None,
    now: dt.datetime | None = None,
) -> SnapshotManifest:
    """Build, validate and atomically publish one versioned dashboard snapshot."""
    settings = settings or get_settings()
    now = now or dt.datetime.now(dt.UTC)
    version = version or _version(now)
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"f1-dashboard-{version}.duckdb"
    if final_path.exists():
        raise FileExistsError(f"snapshot version already exists: {version}")

    descriptor, temporary_name = tempfile.mkstemp(
        dir=output_dir, prefix=f".{version}.", suffix=".duckdb"
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    try:
        table_rows = (
            _copy_duckdb(settings.duckdb_path, temporary)
            if settings.warehouse == "duckdb"
            else _copy_postgres(settings, temporary)
        )
        latest_event_date = validate_dashboard_snapshot(temporary)
        _write_snapshot_metadata(
            temporary,
            version=version,
            generated_at=now,
            source=settings.warehouse,
            latest_event_date=latest_event_date,
        )
        os.replace(temporary, final_path)
    finally:
        temporary.unlink(missing_ok=True)

    manifest = SnapshotManifest(
        version=version,
        generated_at=now.isoformat(),
        source=settings.warehouse,
        database_file=final_path.name,
        sha256=_sha256(final_path),
        size_bytes=final_path.stat().st_size,
        latest_event_date=latest_event_date,
        table_rows=table_rows,
    )
    manifest_path = output_dir / f"f1-dashboard-{version}.json"
    _write_json(asdict(manifest), manifest_path)
    _atomic_copy(final_path, output_dir / "latest.duckdb")
    _write_json(asdict(manifest), output_dir / "latest.json")
    if publish_uri:
        _publish(final_path, manifest_path, publish_uri, version)
    return manifest


def fetch_dashboard_snapshot(uri: str, output: Path) -> SnapshotManifest:
    """Resolve ``latest.json``, verify its immutable database and install it locally."""
    import fsspec

    base = uri.rstrip("/")
    filesystem, root = fsspec.core.url_to_fs(base)
    with filesystem.open(f"{root.rstrip('/')}/latest.json", "rb") as handle:
        payload = json.load(handle)
    manifest = SnapshotManifest(**payload)
    remote = f"{root.rstrip('/')}/{manifest.version}/{manifest.database_file}"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        filesystem.get(remote, str(temporary))
        if _sha256(temporary) != manifest.sha256:
            raise ValueError("downloaded dashboard snapshot checksum does not match its manifest")
        validate_dashboard_snapshot(temporary)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    _write_json(asdict(manifest), output.with_suffix(".json"))
    return manifest

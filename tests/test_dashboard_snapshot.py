from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb
import pytest
from ingestion.config import Settings
from ingestion.dashboard_snapshot import (
    DASHBOARD_CONTRACT,
    build_dashboard_snapshot,
    fetch_dashboard_snapshot,
)


def _warehouse(path: Path) -> None:
    connection = duckdb.connect(str(path))
    try:
        for schema in ("staging", "intermediate", "marts"):
            connection.execute(f"create schema {schema}")
        duck_type = {
            "season": "integer",
            "round": "integer",
            "lap_number": "integer",
            "stint": "integer",
            "start_lap": "integer",
            "end_lap": "integer",
            "n_laps": "integer",
            "n_comparisons": "integer",
            "eligible_laps": "integer",
            "clean_air_laps": "integer",
            "traffic_laps": "integer",
            "mixed_laps": "integer",
            "matched_traffic_laps": "integer",
            "context_samples": "integer",
            "valid_context_samples": "integer",
            "traffic_samples": "integer",
            "matched_clean_laps": "integer",
            "candidate_laps": "integer",
            "modelled_laps": "integer",
            "excluded_laps": "integer",
            "candidate_stints": "integer",
            "modelled_stints": "integer",
            "unexplained_slow_laps": "integer",
            "stint_clean_laps": "integer",
            "out_lap": "integer",
            "stint_start_lap": "integer",
            "stint_end_lap": "integer",
            "stint_laps": "integer",
            "clean_evaluation_laps": "integer",
            "traffic_evaluation_laps": "integer",
            "mature_reference_laps": "integer",
            "stable_window_start_lap": "integer",
            "time_to_pace_laps": "integer",
            "post_stop_offset": "integer",
            "pit_lap": "integer",
            "stop_number": "integer",
            "early_pit_lap": "integer",
            "late_pit_lap": "integer",
            "stop_separation_laps": "integer",
            "checkpoint_before_lap": "integer",
            "checkpoint_after_lap": "integer",
            "position_before_early": "integer",
            "position_before_late": "integer",
            "position_after_early": "integer",
            "position_after_late": "integer",
            "event_number": "integer",
            "deployment_lap": "integer",
            "post_checkpoint_lap": "integer",
            "pre_driver_count": "integer",
            "post_driver_count": "integer",
            "eligible_driver_count": "integer",
            "intervention_stop_count": "integer",
            "recovery_stop_count": "integer",
            "position_gainer_count": "integer",
            "position_loser_count": "integer",
            "position_before": "integer",
            "position_after": "integer",
            "positions_gained": "integer",
            "lap_before": "integer",
            "lap_after": "integer",
            "lap_deficit_before": "integer",
            "lap_deficit_after": "integer",
            "stint_before": "integer",
            "stint_after": "integer",
            "tyre_life_before": "integer",
            "tyre_life_after": "integer",
            "stop_count": "integer",
            "race_date": "date",
            "rating": "double",
            "rating_lo": "double",
            "rating_hi": "double",
            "form_delta": "double",
            "quali_rating": "double",
            "race_rating": "double",
            "delta": "double",
            "mean_pace_gap": "double",
            "pace_gap": "double",
            "lap_start_sec": "double",
            "session_time_sec": "double",
            "lap_time_sec": "double",
            "traffic_share": "double",
            "clean_air_share": "double",
            "traffic_exposure_pct": "double",
            "replay_coverage_pct": "double",
            "median_gap_to_ahead_s": "double",
            "peer_lap_avg_sec": "double",
            "controlled_pace_delta_sec": "double",
            "matched_clean_delta_sec": "double",
            "paired_traffic_delta_sec": "double",
            "baseline_slope_sec_per_lap": "double",
            "baseline_intercept_sec": "double",
            "baseline_mad_sec": "double",
            "first_flying_warmup_loss_sec": "double",
            "second_flying_warmup_loss_sec": "double",
            "first_two_lap_warmup_cost_sec": "double",
            "stable_band_sec": "double",
            "expected_mature_delta_sec": "double",
            "warmup_loss_sec": "double",
            "observed_controlled_pace_delta_sec": "double",
            "clean_air_controlled_pace_delta_sec": "double",
            "traffic_adjusted_pace_delta_sec": "double",
            "traffic_controlled_pace_delta_sec": "double",
            "traffic_associated_delta_sec_per_lap": "double",
            "traffic_associated_p25_sec": "double",
            "traffic_associated_p75_sec": "double",
            "robust_consistency_sec": "double",
            "robust_consistency_pct": "double",
            "p90_slow_tail_sec": "double",
            "slow_lap_threshold_sec": "double",
            "unexplained_slow_lap_share_pct": "double",
            "unexplained_slow_lap_cost_sec": "double",
            "slow_lap_cost_per_10_laps_sec": "double",
            "worst_residual_sec": "double",
            "expected_controlled_pace_delta_sec": "double",
            "pace_residual_sec": "double",
            "absolute_residual_sec": "double",
            "unexplained_slow_excess_sec": "double",
            "stint_slope_sec_per_tyre_lap": "double",
            "stint_intercept_sec": "double",
            "traffic_gap_threshold_s": "double",
            "clean_air_gap_threshold_s": "double",
            "duration_sec": "double",
            "gap_before_sec": "double",
            "gap_after_sec": "double",
            "net_time_gain_sec": "double",
            "early_stop_duration_sec": "double",
            "late_stop_duration_sec": "double",
            "stop_duration_delta_sec": "double",
            "on_track_gain_sec": "double",
            "start_t_s": "double",
            "end_t_s": "double",
            "post_checkpoint_t_s": "double",
            "duration_s": "double",
            "gap_to_leader_before_s": "double",
            "gap_to_leader_after_s": "double",
            "raw_gap_gain_s": "double",
            "field_adjusted_gap_gain_s": "double",
            "timing_before_offset_s": "double",
            "timing_after_offset_s": "double",
            "early_new_tyre_fresh": "boolean",
            "late_new_tyre_fresh": "boolean",
            "position_flip": "boolean",
            "window_green": "boolean",
            "recovery_clean": "boolean",
            "lap_deficit_changed": "boolean",
            "pitted_during_intervention": "boolean",
            "pitted_during_recovery": "boolean",
            "tyre_changed_during_suspension": "boolean",
            "active_after": "boolean",
            "eligible": "boolean",
            "is_fresh_tyre": "boolean",
            "contiguous_stint_transition": "boolean",
            "stable_pace_achieved": "boolean",
            "right_censored": "boolean",
            "observation_complete": "boolean",
            "warmup_eligible": "boolean",
            "crossover_eligible": "boolean",
            "used_for_baseline": "boolean",
            "within_stable_band": "boolean",
            "lap_eligible": "boolean",
            "consistency_eligible": "boolean",
            "is_unexplained_slow_lap": "boolean",
            "top_speed_kph": "double",
            "deg_sec_per_lap": "double",
            "distance_m": "double",
            "speed_kph": "double",
            "t_s": "double",
            "x": "double",
            "y": "double",
        }
        for (schema, table), columns in DASHBOARD_CONTRACT.items():
            definitions = ", ".join(
                f'"{column}" {duck_type.get(column, "varchar")}' for column in sorted(columns)
            )
            connection.execute(f'create table {schema}."{table}" ({definitions})')
        connection.execute(
            "insert into staging.stg_races (season, round, race_name, race_date) "
            "values (2026, 1, 'Test Grand Prix', date '2026-08-30'), "
            "(2026, 2, 'Future Grand Prix', date '2026-12-06')"
        )
        connection.execute("insert into marts.mart_lap_times (season, round) values (2026, 1)")
        connection.execute(
            "insert into marts.driver_ratings "
            "(driver_id, rating, rating_lo, rating_hi, n_comparisons) "
            "values ('driver', 1.0, 0.9, 1.1, 10)"
        )
    finally:
        connection.close()


def test_builds_versioned_snapshot_and_latest_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.duckdb"
    _warehouse(source)
    settings = Settings(warehouse="duckdb", duckdb_path=source, lake_dir=tmp_path / "lake")

    manifest = build_dashboard_snapshot(
        tmp_path / "snapshots",
        settings=settings,
        version="test-v1",
        now=dt.datetime(2026, 8, 30, tzinfo=dt.UTC),
    )

    assert manifest.version == "test-v1"
    assert manifest.latest_event_date == "2026-08-30"
    assert manifest.table_rows["marts.driver_ratings"] == 1
    assert (tmp_path / "snapshots/f1-dashboard-test-v1.duckdb").is_file()
    assert (tmp_path / "snapshots/latest.duckdb").is_file()
    payload = json.loads((tmp_path / "snapshots/latest.json").read_text())
    assert payload["sha256"] == manifest.sha256
    with duckdb.connect(str(tmp_path / "snapshots/latest.duckdb"), read_only=True) as connection:
        metadata = connection.execute(
            "select version, source, latest_event_date from dashboard.snapshot_metadata"
        ).fetchone()
    assert metadata == ("test-v1", "duckdb", dt.date(2026, 8, 30))


def test_fetch_verifies_checksum(tmp_path: Path) -> None:
    source = tmp_path / "source.duckdb"
    _warehouse(source)
    settings = Settings(warehouse="duckdb", duckdb_path=source, lake_dir=tmp_path / "lake")
    published = tmp_path / "published"
    manifest = build_dashboard_snapshot(
        tmp_path / "build",
        settings=settings,
        version="test-v2",
        publish_uri=f"file://{published}",
    )

    installed = tmp_path / "installed/latest.duckdb"
    fetched = fetch_dashboard_snapshot(f"file://{published}", installed)
    assert fetched.sha256 == manifest.sha256
    assert installed.is_file()

    (published / manifest.version / manifest.database_file).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        fetch_dashboard_snapshot(f"file://{published}", installed)


def test_snapshot_rejects_incompatible_dashboard_columns(tmp_path: Path) -> None:
    source = tmp_path / "source.duckdb"
    _warehouse(source)
    with duckdb.connect(str(source)) as connection:
        connection.execute("alter table marts.driver_ratings drop column rating_lo")
    settings = Settings(warehouse="duckdb", duckdb_path=source, lake_dir=tmp_path / "lake")

    with pytest.raises(ValueError, match=r"driver_ratings.*rating_lo"):
        build_dashboard_snapshot(
            tmp_path / "snapshots",
            settings=settings,
            version="broken-columns",
        )

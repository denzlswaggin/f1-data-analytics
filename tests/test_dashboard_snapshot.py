from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb
import pytest
from ingestion.config import Settings
from ingestion.dashboard_snapshot import (
    DASHBOARD_CONTRACT,
    SnapshotManifest,
    build_dashboard_snapshot,
    fetch_dashboard_snapshot,
)


def _warehouse(path: Path) -> None:
    connection = duckdb.connect(str(path))
    try:
        for schema in ("staging", "intermediate", "marts"):
            connection.execute(f"create schema {schema}")
        duck_type = {
            "finish_position": "integer",
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
            "first_observed_confirmation_laps": "integer",
            "post_stop_offset": "integer",
            "pit_lap": "integer",
            "stop_number": "integer",
            "actual_pit_lap": "integer",
            "actual_out_lap": "integer",
            "old_stint": "integer",
            "new_stint": "integer",
            "window_start_lap": "integer",
            "window_end_lap": "integer",
            "best_supported_shift_laps": "integer",
            "best_hypothetical_pit_lap": "integer",
            "supported_scenarios": "integer",
            "old_reference_laps": "integer",
            "new_mature_reference_laps": "integer",
            "warmup_profile_laps": "integer",
            "shift_laps": "integer",
            "hypothetical_pit_lap": "integer",
            "hypothetical_out_lap": "integer",
            "old_tyre_extension_laps": "integer",
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
            "checkpoint_order": "integer",
            "running_order": "integer",
            "focus_rank": "integer",
            "sample_size": "integer",
            "deployment_lap": "integer",
            "post_checkpoint_lap": "integer",
            "pre_driver_count": "integer",
            "post_driver_count": "integer",
            "eligible_driver_count": "integer",
            "time_comparable_driver_count": "integer",
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
            "material_effect_count": "integer",
            "evaluated_effect_count": "integer",
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
            "peer_lap_median_sec": "double",
            "peer_count": "integer",
            "bootstrap_requested_samples": "integer",
            "bootstrap_valid_samples": "integer",
            "bootstrap_attempted_samples": "integer",
            "boundary_minimum": "boolean",
            "best_old_extrapolation_laps": "double",
            "best_new_extrapolation_laps": "double",
            "actual_old_extrapolation_laps": "double",
            "actual_new_extrapolation_laps": "double",
            "old_extrapolation_laps": "double",
            "new_extrapolation_laps": "double",
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
            "pit_duration_sec": "double",
            "estimated_gain_vs_actual_sec": "double",
            "best_delta_p25_sec": "double",
            "best_delta_p75_sec": "double",
            "best_shift_win_pct": "double",
            "best_earlier_delta_sec": "double",
            "best_later_delta_sec": "double",
            "old_slope_sec_per_tyre_lap": "double",
            "new_slope_sec_per_stint_lap": "double",
            "old_model_mad_sec": "double",
            "new_model_mad_sec": "double",
            "field_peer_count_median": "double",
            "estimated_cost_index_sec": "double",
            "delta_vs_actual_sec": "double",
            "delta_p25_sec": "double",
            "delta_p75_sec": "double",
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
            "pressure_seconds": "double",
            "longest_pressure_run_s": "double",
            "release_run_s": "double",
            "gap_to_leader_before_s": "double",
            "gap_to_leader_after_s": "double",
            "raw_gap_gain_s": "double",
            "field_adjusted_gap_gain_s": "double",
            "timing_before_offset_s": "double",
            "timing_after_offset_s": "double",
            "pit_in_t_s": "double",
            "pit_out_t_s": "double",
            "checkpoint_t_s": "double",
            "lap_progress": "double",
            "gap_to_leader_s": "double",
            "capture_offset_s": "double",
            "value": "double",
            "lower_bound": "double",
            "upper_bound": "double",
            "early_new_tyre_fresh": "boolean",
            "late_new_tyre_fresh": "boolean",
            "position_flip": "boolean",
            "window_green": "boolean",
            "recovery_clean": "boolean",
            "time_eligible": "boolean",
            "lap_deficit_changed": "boolean",
            "pitted_during_intervention": "boolean",
            "pitted_during_recovery": "boolean",
            "tyre_changed_during_suspension": "boolean",
            "active_after": "boolean",
            "position_eligible": "boolean",
            "gap_eligible": "boolean",
            "pit_eligible": "boolean",
            "restart_eligible": "boolean",
            "tyre_eligible": "boolean",
            "eligible": "boolean",
            "is_pit_in_lap": "boolean",
            "is_pit_out_lap": "boolean",
            "is_pit_boundary": "boolean",
            "official_pit_match": "boolean",
            "new_tyre_fresh": "boolean",
            "supported": "boolean",
            "is_fresh_tyre": "boolean",
            "contiguous_stint_transition": "boolean",
            "stable_pace_achieved": "boolean",
            "confirmation_history_complete": "boolean",
            "clean_air_eligible": "boolean",
            "traffic_association_eligible": "boolean",
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
        connection.execute(
            "create table staging.unused_raw_ticks as select range as tick from range(10)"
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
    assert manifest.schema_version == 2
    assert manifest.git_sha
    assert manifest.package_versions["duckdb"]
    assert manifest.table_rows["marts.driver_ratings"] == 1
    assert "staging.unused_raw_ticks" not in manifest.table_rows
    assert (tmp_path / "snapshots/f1-dashboard-test-v1.duckdb").is_file()
    assert (tmp_path / "snapshots/latest.duckdb").is_file()
    payload = json.loads((tmp_path / "snapshots/latest.json").read_text())
    assert payload["sha256"] == manifest.sha256
    with duckdb.connect(str(tmp_path / "snapshots/latest.duckdb"), read_only=True) as connection:
        served_tables = {
            (str(schema), str(table))
            for schema, table in connection.execute(
                "select table_schema, table_name from information_schema.tables "
                "where table_schema in ('staging', 'intermediate', 'marts')"
            ).fetchall()
        }
        assert served_tables == set(DASHBOARD_CONTRACT)
        assert connection.execute(
            "select count(*) from information_schema.tables "
            "where table_schema = 'staging' and table_name = 'unused_raw_ticks'"
        ).fetchone() == (0,)
        metadata = connection.execute(
            "select version, source, latest_event_date, schema_version, git_sha "
            "from dashboard.snapshot_metadata"
        ).fetchone()
    assert metadata == (
        "test-v1",
        "duckdb",
        dt.date(2026, 8, 30),
        2,
        manifest.git_sha,
    )


def test_legacy_snapshot_manifest_remains_loadable() -> None:
    manifest = SnapshotManifest(
        version="legacy",
        generated_at="2026-01-01T00:00:00+00:00",
        source="duckdb",
        database_file="legacy.duckdb",
        sha256="abc",
        size_bytes=123,
        latest_event_date=None,
        table_rows={},
    )

    assert manifest.schema_version == 2
    assert manifest.git_sha is None
    assert manifest.package_versions == {}


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


@pytest.mark.parametrize("table", ["race_control_events", "race_control_impact"])
def test_race_control_sources_preserve_time_eligibility_schema(tmp_path: Path, table: str) -> None:
    source = tmp_path / "source.duckdb"
    _warehouse(source)
    query = (
        Path(__file__).resolve().parents[1] / "dashboard" / "sources" / "f1" / f"{table}.sql"
    ).read_text(encoding="utf-8")
    with duckdb.connect(str(source)) as connection:
        connection.execute(f"delete from marts.{table}")
        result = connection.execute(query).fetchdf()
        assert len(result) == 1
        sentinel = result.iloc[0]
        assert sentinel["season"] == 0
        assert sentinel["time_comparable_driver_count"] == 0
        assert not sentinel["time_eligible"]
        assert sentinel["time_exclusion_reason"] == "No data"
        assert sentinel["methodology_version"] == "race-control-impact-v3"

        connection.execute(
            f"insert into marts.{table} "
            "(season, round, time_comparable_driver_count, time_eligible, "
            "time_exclusion_reason, eligible, methodology_version) "
            "values (2025, 1, 4, false, 'Insufficient comparable cohort', true, "
            "'race-control-impact-v3')"
        )
        result = connection.execute(query).fetchdf()
        assert len(result) == 1
        row = result.iloc[0]
        assert row["season"] == 2025
        assert row["eligible"]
        assert row["time_comparable_driver_count"] == 4
        assert not row["time_eligible"]
        assert row["time_exclusion_reason"] == "Insufficient comparable cohort"


@pytest.mark.parametrize("table", ["race_control_checkpoints", "race_control_effects"])
def test_race_control_detail_sources_have_typed_empty_sentinel(tmp_path: Path, table: str) -> None:
    source = tmp_path / "source.duckdb"
    _warehouse(source)
    query = (
        Path(__file__).resolve().parents[1] / "dashboard" / "sources" / "f1" / f"{table}.sql"
    ).read_text(encoding="utf-8")
    with duckdb.connect(str(source)) as connection:
        result = connection.execute(query).fetchdf()
    assert len(result) == 1
    assert result.iloc[0]["season"] == 0
    assert not result.iloc[0]["eligible"]
    assert result.iloc[0]["methodology_version"] == "race-control-impact-v3"


@pytest.mark.parametrize("table", ["racecraft_battles", "racecraft_driver_summary"])
def test_racecraft_sources_execute_empty_and_populated_schema(tmp_path: Path, table: str) -> None:
    source = tmp_path / "source.duckdb"
    _warehouse(source)
    query = (
        Path(__file__).resolve().parents[1] / "dashboard" / "sources" / "f1" / f"{table}.sql"
    ).read_text(encoding="utf-8")
    with duckdb.connect(str(source)) as connection:
        connection.execute(f"delete from marts.{table}")
        result = connection.execute(query).fetchdf()
        assert len(result) == 1
        assert result.iloc[0]["season"] == 0
        assert result.iloc[0]["methodology_version"] == "racecraft-v3-continuity"
        if table == "racecraft_battles":
            for field in ("pressure_seconds", "longest_pressure_run_s", "release_run_s"):
                assert result[field].isna().all()
                assert result[field].dtype.kind == "f"
            connection.execute(
                "insert into marts.racecraft_battles "
                "(season, round, pressure_seconds, longest_pressure_run_s, release_run_s, "
                "methodology_version) values (2025, 1, 24.0, 12.0, 15.0, "
                "'racecraft-v3-continuity')"
            )
        else:
            connection.execute(
                "insert into marts.racecraft_driver_summary "
                "(season, round, methodology_version) "
                "values (2025, 1, 'racecraft-v3-continuity')"
            )
        result = connection.execute(query).fetchdf()
        assert len(result) == 1
        assert result.iloc[0]["season"] == 2025
        assert result.iloc[0]["methodology_version"] == "racecraft-v3-continuity"
        if table == "racecraft_battles":
            assert result.iloc[0]["pressure_seconds"] == 24.0
            assert result.iloc[0]["longest_pressure_run_s"] == 12.0
            assert result.iloc[0]["release_run_s"] == 15.0
